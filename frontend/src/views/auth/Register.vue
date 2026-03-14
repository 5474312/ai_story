<template>
  <div class="min-h-screen flex items-center justify-center bg-base-200 py-12 px-4 sm:px-6 lg:px-8">
    <div class="card w-full max-w-md bg-base-100 shadow-xl">
      <div class="card-body">
        <!-- Logo和标题 -->
        <div class="text-center mb-6">
          <h1 class="text-3xl font-bold text-primary">
            AI Story
          </h1>
          <p class="text-base-content/70 mt-2">
            创建新账户
          </p>
        </div>

        <!-- 注册表单 -->
        <form @submit.prevent="handleSubmit">
          <!-- 用户名 -->
          <div class="form-control mb-4">
            <label class="label">
              <span class="label-text">用户名</span>
            </label>
            <input
              v-model="form.username"
              type="text"
              placeholder="请输入用户名"
              class="input input-bordered"
              :class="{ 'input-error': errors.username }"
              required
            >
            <label
              v-if="errors.username"
              class="label"
            >
              <span class="label-text-alt text-error">{{ errors.username }}</span>
            </label>
          </div>

          <!-- 邮箱 -->
          <div class="form-control mb-4">
            <label class="label">
              <span class="label-text">邮箱</span>
            </label>
            <input
              v-model="form.email"
              type="email"
              placeholder="请输入邮箱"
              class="input input-bordered"
              :class="{ 'input-error': errors.email }"
              required
            >
            <label
              v-if="errors.email"
              class="label"
            >
              <span class="label-text-alt text-error">{{ errors.email }}</span>
            </label>
          </div>

          <!-- 密码 -->
          <div class="form-control mb-4">
            <label class="label">
              <span class="label-text">密码</span>
            </label>
            <input
              v-model="form.password"
              type="password"
              placeholder="至少6位密码"
              class="input input-bordered"
              :class="{ 'input-error': errors.password }"
              required
            >
            <label
              v-if="errors.password"
              class="label"
            >
              <span class="label-text-alt text-error">{{ errors.password }}</span>
            </label>
          </div>

          <!-- 确认密码 -->
          <div class="form-control mb-6">
            <label class="label">
              <span class="label-text">确认密码</span>
            </label>
            <input
              v-model="form.password_confirm"
              type="password"
              placeholder="请再次输入密码"
              class="input input-bordered"
              :class="{ 'input-error': errors.password_confirm }"
              required
            >
            <label
              v-if="errors.password_confirm"
              class="label"
            >
              <span class="label-text-alt text-error">{{ errors.password_confirm }}</span>
            </label>
          </div>

          <!-- 错误提示 -->
          <div
            v-if="errorMessage"
            class="alert alert-error mb-4"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="stroke-current shrink-0 h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>{{ errorMessage }}</span>
          </div>

          <!-- 注册按钮 -->
          <button
            type="submit"
            class="btn btn-primary w-full"
            :class="{ 'loading': loading }"
            :disabled="loading"
          >
            {{ loading ? '注册中...' : '注册' }}
          </button>
        </form>

        <!-- 底部链接 -->
        <div class="divider">
          或
        </div>
        <div class="text-center">
          <p class="text-sm text-base-content/70">
            已有账户？
            <router-link
              to="/login"
              class="link link-primary"
            >
              立即登录
            </router-link>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { mapActions } from 'vuex'

export default {
  name: 'Register',
  data() {
    return {
      form: {
        username: '',
        email: '',
        password: '',
        password_confirm: ''
      },
      errors: {},
      errorMessage: '',
      loading: false
    }
  },
  methods: {
    ...mapActions('auth', ['register']),

    async handleSubmit() {
      // 清空错误
      this.errors = {}
      this.errorMessage = ''

      // 表单验证
      if (!this.form.username) {
        this.errors.username = '请输入用户名'
        return
      }
      if (!this.form.email) {
        this.errors.email = '请输入邮箱'
        return
      }
      if (!this.form.password) {
        this.errors.password = '请输入密码'
        return
      }
      if (this.form.password.length < 6) {
        this.errors.password = '密码至少6位'
        return
      }
      if (this.form.password !== this.form.password_confirm) {
        this.errors.password_confirm = '两次密码输入不一致'
        return
      }

      this.loading = true

      try {
        await this.register(this.form)

        // 注册成功，跳转到首页
        this.$router.push('/')
      } catch (error) {
        console.error('注册失败:', error)

        // 处理后端验证错误
        if (error.response && error.response.data) {
          const data = error.response.data
          if (data.username) {
            this.errors.username = Array.isArray(data.username) ? data.username[0] : data.username
          }
          if (data.email) {
            this.errors.email = Array.isArray(data.email) ? data.email[0] : data.email
          }
          if (data.password) {
            this.errors.password = Array.isArray(data.password) ? data.password[0] : data.password
          }
          if (data.password_confirm) {
            this.errors.password_confirm = Array.isArray(data.password_confirm) ? data.password_confirm[0] : data.password_confirm
          }
          this.errorMessage = data.message || '注册失败，请检查表单'
        } else {
          this.errorMessage = error.message || '注册失败，请稍后重试'
        }
      } finally {
        this.loading = false
      }
    }
  }
}
</script>

<style scoped>
/* 额外的样式可以在这里添加 */
</style>
