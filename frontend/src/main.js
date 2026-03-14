import Vue from 'vue';
import '@/assets/css/main.css';
import './output.css'

import App from './App.vue';
import router from './router';
import store from './store';
import message from '@/utils/message';
import confirm from '@/utils/confirm';

// 全局配置
Vue.config.productionTip = false;

// 注册全局消息提示
Vue.prototype.$message = message;

// 全局confirm对话框
Vue.prototype.$confirm = (msg, title = '确认', options = {}) => confirm.open(msg, title, options);
Vue.prototype.$alert = (msg, title = '提示', options = {}) => confirm.alert(msg, title, options);

// 全局错误处理
Vue.config.errorHandler = (err, vm, info) => {
  console.error('Vue Error:', err, info);
};

// 创建 Vue 实例
const app = new Vue({
  router,
  store,
  render: (h) => h(App),
}).$mount('#app');

// 初始化主题
const savedTheme = store.getters['ui/theme'];
if (savedTheme) {
  app.$el.setAttribute('data-theme', savedTheme);
}
