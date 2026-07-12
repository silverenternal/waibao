/**
 * T1203 — shared components.
 *
 * Using easycom: components in `src/components/wb-<name>/` are auto-imported.
 * Just write `<wb-empty />` etc. in any template.
 */
import Empty from './wb-empty/wb-empty.vue';
import Loading from './wb-loading/wb-loading.vue';
import Card from './wb-card/wb-card.vue';

export { Empty, Loading, Card };