import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        {
          path: '',
          redirect: '/dashboard',
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/Dashboard/DashboardView.vue'),
          meta: { title: '系统概览' },
        },
        {
          path: 'knowledge-base',
          name: 'knowledge-base',
          component: () => import('@/views/KnowledgeBase/KnowledgeBaseView.vue'),
          meta: { title: '文档管理' },
        },
        {
          path: 'assistant',
          name: 'assistant',
          component: () => import('@/views/Assistant/AssistantView.vue'),
          meta: { title: '智能问答' },
        },
        {
          path: 'workflow',
          name: 'workflow',
          component: () => import('@/views/Workflow/WorkflowView.vue'),
          meta: { title: '执行过程' },
        },
        {
          path: 'approval',
          name: 'approval',
          component: () => import('@/views/Approval/ApprovalView.vue'),
          meta: { title: '人工审批' },
        },
        {
          path: 'trace',
          name: 'trace',
          component: () => import('@/views/Trace/TraceView.vue'),
          meta: { title: '运行追踪' },
        },
      ],
    },
  ],
})

export default router
