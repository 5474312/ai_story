<template>
  <div class="prompt-set-form">
    <PageCard :title="isEdit ? '编辑提示词集' : '创建提示词集'">
      <template #header-right>
        <div class="flex gap-2">
          <button
            class="btn btn-ghost btn-sm"
            @click="handleCancel"
          >
            取消
          </button>
          <button
            class="btn btn-primary btn-sm"
            :disabled="submitting || !isFormValid"
            @click="handleSubmit"
          >
            <span
              v-if="submitting"
              class="loading loading-spinner loading-sm"
            />
            {{ isEdit ? '保存' : '创建' }}
          </button>
        </div>
      </template>

      <LoadingContainer :loading="loading">
        <form
          class="space-y-6"
          @submit.prevent="handleSubmit"
        >
          <!-- 基本信息 -->
          <div class="card bg-base-100 border border-base-300">
            <div class="card-body">
              <h3 class="card-title text-base mb-4">
                基本信息
              </h3>

              <!-- 名称 -->
              <div class="form-control">
                <label class="label">
                  <span class="label-text">
                    名称 <span class="text-error">*</span>
                  </span>
                </label>
                <input
                  v-model="formData.name"
                  type="text"
                  placeholder="请输入提示词集名称"
                  class="input input-bordered"
                  :class="{ 'input-error': errors.name }"
                  required
                >
                <label
                  v-if="errors.name"
                  class="label"
                >
                  <span class="label-text-alt text-error">{{ errors.name }}</span>
                </label>
              </div>

              <!-- 描述 -->
              <div class="form-control">
                <label class="label">
                  <span class="label-text">描述</span>
                </label>
                <textarea
                  v-model="formData.description"
                  placeholder="请输入提示词集描述"
                  class="textarea textarea-bordered h-24"
                  :class="{ 'textarea-error': errors.description }"
                />
                <label
                  v-if="errors.description"
                  class="label"
                >
                  <span class="label-text-alt text-error">{{ errors.description }}</span>
                </label>
              </div>

              <!-- 状态选项 -->
              <div class="form-control">
                <label class="label cursor-pointer justify-start gap-4">
                  <input
                    v-model="formData.is_active"
                    type="checkbox"
                    class="checkbox checkbox-primary"
                  >
                  <span class="label-text">启用此提示词集</span>
                </label>
              </div>

              <!-- 默认选项 (仅管理员) -->
              <div
                v-if="isAdmin"
                class="form-control"
              >
                <label class="label cursor-pointer justify-start gap-4">
                  <input
                    v-model="formData.is_default"
                    type="checkbox"
                    class="checkbox checkbox-primary"
                  >
                  <span class="label-text">设为默认提示词集</span>
                </label>
                <label class="label">
                  <span class="label-text-alt text-base-content/60">
                    默认提示词集将在创建新项目时自动使用
                  </span>
                </label>
              </div>
            </div>
          </div>

          <!-- 错误提示 -->
          <div
            v-if="formError"
            class="alert alert-error"
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
            <span>{{ formError }}</span>
          </div>

          <!-- 成功提示 -->
          <div
            v-if="formSuccess"
            class="alert alert-success"
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
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>{{ formSuccess }}</span>
          </div>
        </form>
      </LoadingContainer>
    </PageCard>
  </div>
</template>

<script>
import { mapState, mapGetters, mapActions } from 'vuex';
import PageCard from '@/components/common/PageCard.vue';
import LoadingContainer from '@/components/common/LoadingContainer.vue';

export default {
  name: 'PromptSetForm',
  components: {
    PageCard,
    LoadingContainer,
  },
  data() {
    return {
      formData: {
        name: '',
        description: '',
        is_active: true,
        is_default: false,
      },
      errors: {},
      formError: '',
      formSuccess: '',
      loading: false,
      submitting: false,
    };
  },
  computed: {
    ...mapState('prompts', {
      currentPromptSet: (state) => state.currentPromptSet,
    }),
    ...mapGetters('auth', {
      currentUser: 'currentUser',
    }),
    isEdit() {
      return !!this.$route.params.id;
    },
    isAdmin() {
      // 检查当前用户是否是管理员
      return this.currentUser?.is_staff || false;
    },
    isFormValid() {
      return this.formData.name.trim().length > 0;
    },
  },
  async created() {
    if (this.isEdit) {
      await this.loadPromptSet();
    }
  },
  methods: {
    ...mapActions('prompts', [
      'fetchPromptSetDetail',
      'createPromptSet',
      'updatePromptSet',
    ]),

    async loadPromptSet() {
      this.loading = true;
      try {
        await this.fetchPromptSetDetail(this.$route.params.id);
        // 填充表单数据
        if (this.currentPromptSet) {
          this.formData = {
            name: this.currentPromptSet.name,
            description: this.currentPromptSet.description || '',
            is_active: this.currentPromptSet.is_active,
            is_default: this.currentPromptSet.is_default,
          };
        }
      } catch (error) {
        console.error('加载提示词集失败:', error);
        this.formError = '加载提示词集失败,请重试';
      } finally {
        this.loading = false;
      }
    },

    validateForm() {
      this.errors = {};
      this.formError = '';

      // 验证名称
      if (!this.formData.name || this.formData.name.trim().length === 0) {
        this.errors.name = '请输入提示词集名称';
      } else if (this.formData.name.length > 100) {
        this.errors.name = '名称长度不能超过100个字符';
      }

      // 验证描述
      if (this.formData.description && this.formData.description.length > 500) {
        this.errors.description = '描述长度不能超过500个字符';
      }

      // 非管理员不能设置默认
      if (this.formData.is_default && !this.isAdmin) {
        this.formError = '只有管理员可以设置默认提示词集';
        return false;
      }

      return Object.keys(this.errors).length === 0 && !this.formError;
    },

    async handleSubmit() {
      if (!this.validateForm()) {
        return;
      }

      this.submitting = true;
      this.formError = '';
      this.formSuccess = '';

      try {
        if (this.isEdit) {
          // 更新提示词集
          await this.updatePromptSet({
            id: this.$route.params.id,
            data: this.formData,
          });
          this.formSuccess = '提示词集更新成功!';

          // 延迟跳转
          setTimeout(() => {
            this.$router.push(`/prompts/sets/${this.$route.params.id}`);
          }, 1000);
        } else {
          // 创建提示词集
          const newSet = await this.createPromptSet(this.formData);
          this.formSuccess = '提示词集创建成功!';

          // 延迟跳转到详情页
          setTimeout(() => {
            this.$router.push(`/prompts/sets/${newSet.id}`);
          }, 1000);
        }
      } catch (error) {
        console.error('提交表单失败:', error);

        // 处理后端返回的错误
        if (error.response && error.response.data) {
          const errorData = error.response.data;

          // 字段级错误
          if (typeof errorData === 'object') {
            Object.keys(errorData).forEach((key) => {
              if (key in this.formData) {
                this.errors[key] = Array.isArray(errorData[key])
                  ? errorData[key][0]
                  : errorData[key];
              } else {
                this.formError = Array.isArray(errorData[key])
                  ? errorData[key][0]
                  : errorData[key];
              }
            });
          } else {
            this.formError = errorData.detail || '提交失败,请重试';
          }
        } else {
          this.formError = this.isEdit ? '更新提示词集失败,请重试' : '创建提示词集失败,请重试';
        }
      } finally {
        this.submitting = false;
      }
    },

    handleCancel() {
      if (this.isEdit) {
        this.$router.push(`/prompts/sets/${this.$route.params.id}`);
      } else {
        this.$router.push('/prompts');
      }
    },
  },
};
</script>

<style scoped>
/* 自定义样式 */
</style>
