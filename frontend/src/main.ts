import './assets/base.scss';

import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { router } from './routes';
import App from './App.vue';

const app = createApp(App);

const pinia = createPinia();

app.use(pinia);

app.use(router);

app.directive('focus', {
  mounted: (element) => element.focus(),
});

app.mount('#app');
