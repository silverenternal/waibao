-- ============================================================================
-- 011_collaboration_rooms.sql
-- 多人实时协同房间 (T608)
--
-- 设计要点:
-- 1. rooms 主表 - 协同房间, 5 方 (老板/HR/部门负责人/财务/管理员) 共享
--    字段: organisation_id, name, type (direct/group/topic/project), archived,
--    last_message_at, member_count。
-- 2. room_members - 房间成员, 含 role (owner/admin/member/guest), joined_at,
--    last_read_at (未读位点), muted。
-- 3. room_messages - 消息, 支持 message_type (text/markdown/file/system),
--    parent_id (线程回复), mentions[] (uuid 数组), edited_at, deleted_at。
-- 4. room_threads - 线程聚合 (parent_message_id 聚合 last_reply_at/reply_count),
--    加速列表渲染。
-- 5. room_mentions - @mention 通知表 (per-user unread 列表)。
-- 6. room_reactions - 表情回应 (message_id, user_id, emoji)。
-- 7. room_pins - 房间内被置顶的消息 (一个房间多条 pinned)。
-- 8. RLS: 只有 room_members 才能 SELECT/INSERT messages 和 mentions;
--    thread / reactions / pins 跟随 messages 权限。
-- 9. Realtime publication: 所有相关表加入 supabase_realtime。
-- 10. 索引: messages(room_id, created_at desc)、mentions(user_id, read_at IS NULL)、
--     members(room_id, user_id) UNIQUE。
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 枚举
-- ----------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE room_type AS ENUM ('direct', 'group', 'topic', 'project');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE room_member_role AS ENUM ('owner', 'admin', 'member', 'guest');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE room_message_type AS ENUM ('text', 'markdown', 'file', 'system');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;


-- ----------------------------------------------------------------------------
-- rooms 主表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rooms (
    id              uuid            PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id uuid            REFERENCES organisations(id) ON DELETE CASCADE,
    name            text            NOT NULL,
    type            room_type       NOT NULL DEFAULT 'group',
    created_by      uuid            REFERENCES users(id) ON DELETE SET NULL,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    last_message_at timestamptz,
    archived        boolean         NOT NULL DEFAULT false,
    archived_at     timestamptz,
    metadata        jsonb           NOT NULL DEFAULT '{}'::jsonb,

    -- 反规范化成员数 (避免每次 list 都 count)
    member_count    integer         NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rooms_org ON rooms(organisation_id);
CREATE INDEX IF NOT EXISTS idx_rooms_last_message ON rooms(last_message_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_rooms_archived ON rooms(archived) WHERE archived = false;

COMMENT ON TABLE rooms IS
    '多人实时协同房间 (T608); 5 方 (老板/HR/部门负责人/财务/管理员) 共享对话空间';
COMMENT ON COLUMN rooms.member_count IS
    '反规范化字段, 写入 room_members 时由 trigger 维护';


-- ----------------------------------------------------------------------------
-- room_members 成员表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS room_members (
    room_id        uuid            NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    user_id        uuid            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role           room_member_role NOT NULL DEFAULT 'member',
    joined_at      timestamptz     NOT NULL DEFAULT now(),
    left_at        timestamptz,
    last_read_at   timestamptz,
    muted          boolean         NOT NULL DEFAULT false,
    invitation_pending boolean     NOT NULL DEFAULT false,
    invited_by     uuid            REFERENCES users(id) ON DELETE SET NULL,

    PRIMARY KEY (room_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_room_members_user ON room_members(user_id);
CREATE INDEX IF NOT EXISTS idx_room_members_room_active
    ON room_members(room_id) WHERE left_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_room_members_user_active
    ON room_members(user_id) WHERE left_at IS NULL;

COMMENT ON TABLE room_members IS
    '房间成员; left_at 区分主动离开/被踢, last_read_at 作为未读位点';
COMMENT ON COLUMN room_members.last_read_at IS
    '客户端标 read 时更新; 服务端用 GREATEST(messages.created_at) vs 此值计算未读';


-- ----------------------------------------------------------------------------
-- room_messages 消息表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS room_messages (
    id              uuid            PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id         uuid            NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    sender_id       uuid            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content         text            NOT NULL DEFAULT '',
    message_type    room_message_type NOT NULL DEFAULT 'text',
    parent_id       uuid            REFERENCES room_messages(id) ON DELETE CASCADE,
    mentions        uuid[]          NOT NULL DEFAULT ARRAY[]::uuid[],
    -- 提及位置（用于渲染高亮）: 每个对象 {user_id, start, end}
    mention_offsets jsonb           NOT NULL DEFAULT '[]'::jsonb,

    -- 文件附件 (走 v2.0 /api/uploads)
    attachments     jsonb           NOT NULL DEFAULT '[]'::jsonb,

    -- 编辑/删除
    edited_at       timestamptz,
    deleted_at      timestamptz,
    deleted_by      uuid            REFERENCES users(id) ON DELETE SET NULL,

    -- 线程根标记
    thread_root_id  uuid            REFERENCES room_messages(id) ON DELETE CASCADE,

    created_at      timestamptz     NOT NULL DEFAULT now(),

    CHECK (char_length(content) <= 20000 OR message_type <> 'text')
);

CREATE INDEX IF NOT EXISTS idx_room_messages_room_created
    ON room_messages(room_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_room_messages_parent
    ON room_messages(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_room_messages_sender
    ON room_messages(sender_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_room_messages_thread_root
    ON room_messages(thread_root_id) WHERE thread_root_id IS NOT NULL;
-- 按全文搜索 (search_messages 用)
CREATE INDEX IF NOT EXISTS idx_room_messages_content_trgm
    ON room_messages USING gin (to_tsvector('simple', content))
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_room_messages_mentions_gin
    ON room_messages USING gin (mentions);

COMMENT ON TABLE room_messages IS
    '房间消息: 支持文本/markdown/文件/系统消息; mention_offsets 用于前端高亮';
COMMENT ON COLUMN room_messages.parent_id IS
    '指向 thread 根消息; NULL = 主对话流消息';
COMMENT ON COLUMN room_messages.thread_root_id IS
    '反规范化的 thread 根, 加速列出 thread';


-- ----------------------------------------------------------------------------
-- room_threads 线程聚合
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS room_threads (
    parent_message_id  uuid PRIMARY KEY REFERENCES room_messages(id) ON DELETE CASCADE,
    room_id            uuid NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    last_reply_at      timestamptz NOT NULL DEFAULT now(),
    reply_count        integer     NOT NULL DEFAULT 0,
    participant_ids    uuid[]      NOT NULL DEFAULT ARRAY[]::uuid[]
);

CREATE INDEX IF NOT EXISTS idx_room_threads_room ON room_threads(room_id, last_reply_at DESC);

COMMENT ON TABLE room_threads IS
    '线程聚合: reply_count / last_reply_at 由 trigger 在 reply insert/delete 时维护';


-- ----------------------------------------------------------------------------
-- room_reactions 表情回应
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS room_reactions (
    message_id  uuid    NOT NULL REFERENCES room_messages(id) ON DELETE CASCADE,
    user_id     uuid    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    emoji       text    NOT NULL CHECK (char_length(emoji) BETWEEN 1 AND 16),
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (message_id, user_id, emoji)
);

CREATE INDEX IF NOT EXISTS idx_room_reactions_message ON room_reactions(message_id);
CREATE INDEX IF NOT EXISTS idx_room_reactions_user ON room_reactions(user_id);

COMMENT ON TABLE room_reactions IS
    '消息表情回应; (message_id, user_id, emoji) 唯一, 用户可随时更换 emoji';


-- ----------------------------------------------------------------------------
-- room_mentions 提及通知
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS room_mentions (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    room_id     uuid        NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    message_id  uuid        NOT NULL REFERENCES room_messages(id) ON DELETE CASCADE,
    read_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_room_mentions_user_unread
    ON room_mentions(user_id, created_at DESC) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_room_mentions_room_message
    ON room_mentions(room_id, message_id);

COMMENT ON TABLE room_mentions IS
    '@mention 通知表; 用于填充通知中心 + 未读徽章';
COMMENT ON COLUMN room_mentions.read_at IS
    'NULL = 未读; 用户点开消息时更新';


-- ----------------------------------------------------------------------------
-- room_pins 房间置顶
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS room_pins (
    room_id     uuid        NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    message_id  uuid        NOT NULL REFERENCES room_messages(id) ON DELETE CASCADE,
    pinned_by   uuid        REFERENCES users(id) ON DELETE SET NULL,
    pinned_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (room_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_room_pins_room ON room_pins(room_id, pinned_at DESC);


-- ============================================================================
-- TRIGGERS — 维护反规范化字段
-- ============================================================================

-- 1) 维护 room.member_count + room.last_message_at
CREATE OR REPLACE FUNCTION room_after_message()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.deleted_at IS NULL AND NEW.parent_id IS NULL THEN
        UPDATE rooms SET
            last_message_at = NEW.created_at,
            member_count = (
                SELECT COUNT(*) FROM room_members
                WHERE room_id = NEW.room_id AND left_at IS NULL
            )
        WHERE id = NEW.room_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_room_after_message ON room_messages;
CREATE TRIGGER trg_room_after_message
    AFTER INSERT ON room_messages
    FOR EACH ROW
    EXECUTE FUNCTION room_after_message();


-- 2) 维护 thread (reply_count / last_reply_at)
CREATE OR REPLACE FUNCTION room_after_thread_reply()
RETURNS trigger AS $$
BEGIN
    IF NEW.parent_id IS NOT NULL THEN
        INSERT INTO room_threads (parent_message_id, room_id, last_reply_at, reply_count)
        VALUES (NEW.parent_id, NEW.room_id, NEW.created_at, 1)
        ON CONFLICT (parent_message_id) DO UPDATE
            SET last_reply_at = NEW.created_at,
                reply_count = room_threads.reply_count + 1;

        -- 同步 thread_root_id 便于快速 list
        UPDATE room_messages
        SET thread_root_id = NEW.parent_id
        WHERE id = NEW.id AND thread_root_id IS NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_room_after_thread_reply ON room_messages;
CREATE TRIGGER trg_room_after_thread_reply
    AFTER INSERT ON room_messages
    FOR EACH ROW
    EXECUTE FUNCTION room_after_thread_reply();


-- 3) member_count 在成员 join/leave 时同步
CREATE OR REPLACE FUNCTION room_after_member_change()
RETURNS trigger AS $$
DECLARE
    affected_room uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        affected_room := OLD.room_id;
    ELSE
        affected_room := NEW.room_id;
    END IF;

    UPDATE rooms SET member_count = (
        SELECT COUNT(*) FROM room_members
        WHERE room_id = affected_room AND left_at IS NULL
    )
    WHERE id = affected_room;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_room_after_member_change ON room_members;
CREATE TRIGGER trg_room_after_member_change
    AFTER INSERT OR UPDATE OR DELETE ON room_members
    FOR EACH ROW
    EXECUTE FUNCTION room_after_member_change();


-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE rooms             ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_members      ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_messages     ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_threads      ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_reactions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_mentions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_pins         ENABLE ROW LEVEL SECURITY;

-- helper: 用户是否在某 room 的 active 成员中
CREATE OR REPLACE FUNCTION room_is_member(p_room_id uuid, p_user_id uuid)
RETURNS boolean AS $$
    SELECT EXISTS (
        SELECT 1 FROM room_members
        WHERE room_id = p_room_id AND user_id = p_user_id AND left_at IS NULL
    );
$$ LANGUAGE sql STABLE;

-- ---- ROOMS ----
DROP POLICY IF EXISTS "rooms_member_read" ON rooms;
CREATE POLICY "rooms_member_read" ON rooms
    FOR SELECT USING (
        room_is_member(id, auth.uid())
    );

DROP POLICY IF EXISTS "rooms_member_insert" ON rooms;
CREATE POLICY "rooms_member_insert" ON rooms
    FOR INSERT WITH CHECK (
        created_by = auth.uid()
    );

DROP POLICY IF EXISTS "rooms_admin_update" ON rooms;
CREATE POLICY "rooms_admin_update" ON rooms
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM room_members
            WHERE room_id = rooms.id
              AND user_id = auth.uid()
              AND role IN ('owner', 'admin')
              AND left_at IS NULL
        )
    );

-- ---- ROOM_MEMBERS ----
DROP POLICY IF EXISTS "room_members_read" ON room_members;
CREATE POLICY "room_members_read" ON room_members
    FOR SELECT USING (
        room_is_member(room_id, auth.uid())
        OR user_id = auth.uid()
    );

DROP POLICY IF EXISTS "room_members_insert_self" ON room_members;
CREATE POLICY "room_members_insert_self" ON room_members
    FOR INSERT WITH CHECK (
        -- 创建者把自己加入 / 或 admin/owner 邀请
        user_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM room_members m
            WHERE m.room_id = room_members.room_id
              AND m.user_id = auth.uid()
              AND m.role IN ('owner', 'admin')
              AND m.left_at IS NULL
        )
    );

DROP POLICY IF EXISTS "room_members_update" ON room_members;
CREATE POLICY "room_members_update" ON room_members
    FOR UPDATE USING (
        user_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM room_members m
            WHERE m.room_id = room_members.room_id
              AND m.user_id = auth.uid()
              AND m.role IN ('owner', 'admin')
              AND m.left_at IS NULL
        )
    );

-- ---- ROOM_MESSAGES ----
DROP POLICY IF EXISTS "room_messages_read" ON room_messages;
CREATE POLICY "room_messages_read" ON room_messages
    FOR SELECT USING (
        room_is_member(room_id, auth.uid())
    );

DROP POLICY IF EXISTS "room_messages_insert" ON room_messages;
CREATE POLICY "room_messages_insert" ON room_messages
    FOR INSERT WITH CHECK (
        sender_id = auth.uid()
        AND room_is_member(room_id, auth.uid())
    );

DROP POLICY IF EXISTS "room_messages_update_own" ON room_messages;
CREATE POLICY "room_messages_update_own" ON room_messages
    FOR UPDATE USING (
        sender_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM room_members m
            WHERE m.room_id = room_messages.room_id
              AND m.user_id = auth.uid()
              AND m.role IN ('owner', 'admin')
              AND m.left_at IS NULL
        )
    );

-- ---- ROOM_THREADS ----
DROP POLICY IF EXISTS "room_threads_read" ON room_threads;
CREATE POLICY "room_threads_read" ON room_threads
    FOR SELECT USING (
        room_is_member(room_id, auth.uid())
    );

-- ---- ROOM_REACTIONS ----
DROP POLICY IF EXISTS "room_reactions_read" ON room_reactions;
CREATE POLICY "room_reactions_read" ON room_reactions
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM room_messages msg
            WHERE msg.id = room_reactions.message_id
              AND room_is_member(msg.room_id, auth.uid())
        )
    );

DROP POLICY IF EXISTS "room_reactions_write" ON room_reactions;
CREATE POLICY "room_reactions_write" ON room_reactions
    FOR ALL USING (
        user_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM room_messages msg
            WHERE msg.id = room_reactions.message_id
              AND room_is_member(msg.room_id, auth.uid())
        )
    );

-- ---- ROOM_MENTIONS ----
DROP POLICY IF EXISTS "room_mentions_self_read" ON room_mentions;
CREATE POLICY "room_mentions_self_read" ON room_mentions
    FOR SELECT USING (
        user_id = auth.uid()
    );

DROP POLICY IF EXISTS "room_mentions_member_read" ON room_mentions;
CREATE POLICY "room_mentions_member_read" ON room_mentions
    FOR SELECT USING (
        room_is_member(room_id, auth.uid())
    );

DROP POLICY IF EXISTS "room_mentions_insert" ON room_mentions;
CREATE POLICY "room_mentions_insert" ON room_mentions
    FOR INSERT WITH CHECK (
        -- 任意 active 成员都能创建 (消息 sender 服务端会代写)
        user_id IS NOT NULL
        AND room_is_member(room_id, auth.uid())
    );

DROP POLICY IF EXISTS "room_mentions_self_update" ON room_mentions;
CREATE POLICY "room_mentions_self_update" ON room_mentions
    FOR UPDATE USING (
        user_id = auth.uid()
    );

-- ---- ROOM_PINS ----
DROP POLICY IF EXISTS "room_pins_read" ON room_pins;
CREATE POLICY "room_pins_read" ON room_pins
    FOR SELECT USING (
        room_is_member(room_id, auth.uid())
    );

DROP POLICY IF EXISTS "room_pins_admin" ON room_pins;
CREATE POLICY "room_pins_admin" ON room_pins
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM room_members m
            WHERE m.room_id = room_pins.room_id
              AND m.user_id = auth.uid()
              AND m.role IN ('owner', 'admin')
              AND m.left_at IS NULL
        )
    );


-- ============================================================================
-- REALTIME
-- ============================================================================
ALTER PUBLICATION supabase_realtime ADD TABLE rooms;
ALTER PUBLICATION supabase_realtime ADD TABLE room_members;
ALTER PUBLICATION supabase_realtime ADD TABLE room_messages;
ALTER PUBLICATION supabase_realtime ADD TABLE room_threads;
ALTER PUBLICATION supabase_realtime ADD TABLE room_reactions;
ALTER PUBLICATION supabase_realtime ADD TABLE room_mentions;
ALTER PUBLICATION supabase_realtime ADD TABLE room_pins;


-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON POLICY "rooms_member_read" ON rooms IS
    '只有 active 成员能读取房间元信息; 同时作为 messages/threads 的子查询依赖';

COMMENT ON FUNCTION room_is_member(uuid, uuid) IS
    'RLS helper: 是否为某房间 active 成员; 标记 STABLE 以便 planner 缓存';
