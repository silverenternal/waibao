<script setup lang="ts">
import { onLaunch, onShow, onHide } from '@dcloudio/uni-app';
import { getRuntime, isFeishu } from '@/utils/lark';

onLaunch(() => {
  console.log('[waibao-feishu] Launch, isFeishu=', isFeishu(), getRuntime());
});
onShow(() => { console.log('[waibao-feishu] Show'); });
onHide(() => { console.log('[waibao-feishu] Hide'); });
</script>

<style lang="scss">
page {
  background-color: #F7F8FA;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue', Helvetica, 'Microsoft YaHei', Arial, sans-serif;
  font-size: 28rpx;
  color: #1F2329;
  line-height: 1.5;
}
view, text, button, input, textarea, image, navigator, scroll-view { box-sizing: border-box; }
:root {
  --wb-color-primary: #3370FF;
  --wb-color-success: #00B42A;
  --wb-color-warning: #FF7D00;
  --wb-color-danger: #F53F3F;
}
</style>