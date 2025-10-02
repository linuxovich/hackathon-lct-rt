import { createRouter, createWebHistory } from 'vue-router';

export const router = createRouter({
  routes: [
    {
      path: '/:pathMatch(.*)*',
      component: () => import('@/pages/errors/404.vue'),
      name: '404',
      meta: { title: 'Вы потерялись' },
    },
    {
      path: '/',
      component: () => import('@/pages/Main.vue'),
      redirect: '/document_recognition',
      children: [
        {
          path: '/document_recognition',
          component: () => import('@/pages/DocumentRecognition.vue'),
          meta: { title: 'Распознавание документов' },
        },
      ],
    },
  ],
  history: createWebHistory(),
});

router.beforeEach((to) => {
  const title = to.meta.title as string;
  const defaultTitle = 'Хакатон 2025';

  document.title = title || defaultTitle;
});
