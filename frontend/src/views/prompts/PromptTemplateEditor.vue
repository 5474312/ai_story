<template>
  <div class="prompt-template-editor">
    <PageCard :title="isEdit ? '编辑提示词模板' : '创建提示词模板'">
      <template #header-right>
        <div class="flex gap-2">
          <button
            class="btn btn-ghost btn-sm"
            @click="handleCancel"
          >
            取消
          </button>
          <button
            class="btn btn-ghost btn-sm"
            :disabled="validating"
            @click="handleValidate"
          >
            <span
              v-if="validating"
              class="loading loading-spinner loading-sm"
            />
            验证语法
          </button>
          <button
            class="btn btn-ghost btn-sm"
            :disabled="!canPreview"
            @click="handlePreview"
          >
            预览
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

              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- 提示词集 -->
                <div class="form-control">
                  <label class="label">
                    <span class="label-text">
                      提示词集 <span class="text-error">*</span>
                    </span>
                  </label>
                  <select
                    v-model="formData.template_set"
                    class="select select-bordered"
                    :class="{ 'select-error': errors.template_set }"
                    :disabled="isEdit"
                    required
                  >
                    <option value="">
                      请选择提示词集
                    </option>
                    <option
                      v-for="set in promptSets"
                      :key="set.id"
                      :value="set.id"
                    >
                      {{ set.name }}
                    </option>
                  </select>
                  <label
                    v-if="errors.template_set"
                    class="label"
                  >
                    <span class="label-text-alt text-error">{{ errors.template_set }}</span>
                  </label>
                </div>

                <!-- 阶段类型 -->
                <div class="form-control">
                  <label class="label">
                    <span class="label-text">
                      阶段类型 <span class="text-error">*</span>
                    </span>
                  </label>
                  <select
                    v-model="formData.stage_type"
                    class="select select-bordered"
                    :class="{ 'select-error': errors.stage_type }"
                    :disabled="isEdit"
                    required
                    @change="handleStageTypeChange"
                  >
                    <option value="">
                      请选择阶段
                    </option>
                    <option
                      v-for="stage in stageTypes"
                      :key="stage.value"
                      :value="stage.value"
                    >
                      {{ stage.label }}
                    </option>
                  </select>
                  <label
                    v-if="errors.stage_type"
                    class="label"
                  >
                    <span class="label-text-alt text-error">{{ errors.stage_type }}</span>
                  </label>
                </div>
              </div>

              <!-- AI模型选择 -->
              <div class="form-control">
                <label class="label">
                  <span class="label-text">AI模型</span>
                  <span class="label-text-alt text-base-content/60">
                    为此模板指定默认使用的AI模型
                  </span>
                </label>
                <select
                  v-model="formData.model_provider"
                  class="select select-bordered"
                  :class="{ 'select-error': errors.model_provider }"
                  :disabled="!formData.stage_type || loadingModels"
                >
                  <option value="">
                    无(使用项目配置)
                  </option>
                  <option
                    v-for="model in availableModels"
                    :key="model.id"
                    :value="model.id"
                  >
                    {{ model.name }}
                  </option>
                </select>
                <label class="label">
                  <span class="label-text-alt text-base-content/60">
                    {{ getModelTypeHint() }}
                  </span>
                </label>
                <label
                  v-if="errors.model_provider"
                  class="label"
                >
                  <span class="label-text-alt text-error">{{ errors.model_provider }}</span>
                </label>
              </div>

              <!-- 激活状态 -->
              <div class="form-control">
                <label class="label cursor-pointer justify-start gap-4">
                  <input
                    v-model="formData.is_active"
                    type="checkbox"
                    class="checkbox checkbox-primary"
                  >
                  <span class="label-text">启用此模板</span>
                </label>
              </div>
            </div>
          </div>

          <!-- 模板内容 -->
          <div class="card bg-base-100 border border-base-300">
            <div class="card-body">
              <div class="flex items-center justify-between mb-4">
                <h3 class="card-title text-base">
                  模板内容
                </h3>
                <div class="text-xs text-base-content/60">
                  支持 Jinja2 语法,使引用变量
                </div>
              </div>

              <div class="form-control">
                <textarea
                  v-model="formData.template_content"
                  placeholder="请输入提示词模板内容..."
                  class="textarea textarea-bordered font-mono text-sm h-64"
                  :class="{ 'textarea-error': errors.template_content }"
                  required
                />
                <label
                  v-if="errors.template_content"
                  class="label"
                >
                  <span class="label-text-alt text-error">{{ errors.template_content }}</span>
                </label>
                <label class="label">
                  <span class="label-text-alt">
                    已提取变量: {{ extractedVariables.length > 0 ? extractedVariables.join(', ') : '无' }}
                  </span>
                </label>
              </div>
            </div>
          </div>

          <!-- 变量定义 -->
          <div class="card bg-base-100 border border-base-300">
            <div class="card-body">
              <div class="flex items-center justify-between mb-4">
                <h3 class="card-title text-base">
                  变量定义
                </h3>
                <button
                  type="button"
                  class="btn btn-sm btn-ghost"
                  @click="addVariable"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    class="h-4 w-4 mr-1"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                  >
                    <path
                      fill-rule="evenodd"
                      d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z"
                      clip-rule="evenodd"
                    />
                  </svg>
                  添加变量
                </button>
              </div>

              <!-- 变量列表 -->
              <div
                v-if="variableList.length > 0"
                class="space-y-3"
              >
                <div
                  v-for="(variable, index) in variableList"
                  :key="index"
                  class="grid grid-cols-1 md:grid-cols-12 gap-3 items-start p-3 bg-base-200 rounded-lg"
                >
                  <div class="md:col-span-5 form-control">
                    <input
                      v-model="variable.name"
                      type="text"
                      placeholder="变量名"
                      class="input input-bordered input-sm"
                    >
                  </div>
                  <div class="md:col-span-5 form-control">
                    <select
                      v-model="variable.type"
                      class="select select-bordered select-sm"
                    >
                      <option
                        v-for="type in variableTypes"
                        :key="type.value"
                        :value="type.value"
                      >
                        {{ type.label }}
                      </option>
                    </select>
                  </div>
                  <div class="md:col-span-2 flex items-center">
                    <button
                      type="button"
                      class="btn btn-ghost btn-sm text-error"
                      @click="removeVariable(index)"
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>

              <!-- 空状态 -->
              <div
                v-else
                class="text-center py-8 text-base-content/60 text-sm"
              >
                暂无变量定义,点击"添加变量"按钮创建
              </div>

              <label
                v-if="errors.variables"
                class="label"
              >
                <span class="label-text-alt text-error">{{ errors.variables }}</span>
              </label>
            </div>
          </div>

          <!-- 验证结果 -->
          <div
            v-if="validationResult"
            class="alert"
            :class="validationResult.valid ? 'alert-success' : 'alert-error'"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="stroke-current shrink-0 h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
            >
              <path
                v-if="validationResult.valid"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
              <path
                v-else
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>{{ validationResult.message }}</span>
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

    <!-- 预览对话框 -->
    <dialog
      ref="previewDialog"
      class="modal"
    >
      <div class="modal-box max-w-3xl">
        <h3 class="font-bold text-lg mb-4">
          模板预览
        </h3>

        <!-- 变量输入 -->
        <div
          v-if="variableList.length > 0"
          class="space-y-3 mb-6"
        >
          <h4 class="text-sm font-semibold text-base-content/60">
            输入变量值
          </h4>
          <div
            v-for="variable in variableList"
            :key="variable.name"
            class="form-control"
          >
            <label class="label">
              <span class="label-text">{{ variable.name }} ({{ variable.type }})</span>
            </label>
            <input
              v-model="previewVariables[variable.name]"
              type="text"
              :placeholder="`请输入 ${variable.name}`"
              class="input input-bordered input-sm"
            >
          </div>
        </div>

        <!-- 预览结果 -->
        <div
          v-if="previewResult"
          class="mb-4"
        >
          <h4 class="text-sm font-semibold text-base-content/60 mb-2">
            渲染结果
          </h4>
          <div class="p-4 bg-base-200 rounded-lg">
            <pre class="text-sm whitespace-pre-wrap">{{ previewResult.rendered_content }}</pre>
          </div>
        </div>

        <!-- 预览错误 -->
        <div
          v-if="previewError"
          class="alert alert-error mb-4"
        >
          <span>{{ previewError }}</span>
        </div>

        <div class="modal-action">
          <button
            class="btn"
            @click="$refs.previewDialog.close()"
          >
            关闭
          </button>
          <button
            class="btn btn-primary"
            :disabled="previewing"
            @click="executePreview"
          >
            <span
              v-if="previewing"
              class="loading loading-spinner loading-sm"
            />
            渲染预览
          </button>
        </div>
      </div>
      <form
        method="dialog"
        class="modal-backdrop"
      >
        <button>关闭</button>
      </form>
    </dialog>
  </div>
</template>

<script>
import { mapState, mapActions } from 'vuex';
import PageCard from '@/components/common/PageCard.vue';
import LoadingContainer from '@/components/common/LoadingContainer.vue';
import { STAGE_TYPES, VARIABLE_TYPES } from '@/api/prompts';
import { modelProviderApi } from '@/api/models';

export default {
  name: 'PromptTemplateEditor',
  components: {
    PageCard,
    LoadingContainer,
  },
  data() {
    return {
      formData: {
        template_set: '',
        stage_type: '',
        model_provider: '',
        template_content: '',
        variables: {},
        is_active: true,
      },
      variableList: [], // 变量列表 [{name: '', type: 'string'}]
      errors: {},
      formError: '',
      formSuccess: '',
      loading: false,
      submitting: false,
      validating: false,
      previewing: false,
      loadingModels: false,
      validationResult: null,
      previewVariables: {},
      previewResult: null,
      previewError: '',
      stageTypes: STAGE_TYPES,
      variableTypes: VARIABLE_TYPES,
      availableModels: [], // 可用的AI模型列表
      stageToProviderType: {
        rewrite: 'llm',
        storyboard: 'llm',
        image_generation: 'text2image',
        camera_movement: 'llm',
        video_generation: 'image2video',
      },
    };
  },
  computed: {
    ...mapState('prompts', {
      promptSets: (state) => state.promptSets,
      currentTemplate: (state) => state.currentPromptTemplate,
    }),
    isEdit() {
      return !!this.$route.params.id;
    },
    isFormValid() {
      return (
        this.formData.template_set &&
        this.formData.stage_type &&
        this.formData.template_content.trim().length > 0
      );
    },
    extractedVariables() {
      // 从模板内容中提取变量名
      const regex = /\{\{\s*(\w+)\s*\}\}/g;
      const matches = [];
      let match;
      while ((match = regex.exec(this.formData.template_content)) !== null) {
        if (!matches.includes(match[1])) {
          matches.push(match[1]);
        }
      }
      return matches;
    },
    canPreview() {
      return this.formData.template_content.trim().length > 0;
    },
  },
  watch: {
    // 监听变量列表变化,同步到formData
    variableList: {
      handler(newList) {
        const variables = {};
        newList.forEach((variable) => {
          if (variable.name) {
            variables[variable.name] = variable.type;
          }
        });
        this.formData.variables = variables;
      },
      deep: true,
    },
  },
  async created() {
    // 加载提示词集列表
    await this.fetchPromptSets();

    // 从查询参数获取提示词集和阶段类型
    if (this.$route.query.template_set) {
      this.formData.template_set = this.$route.query.template_set;
    }
    if (this.$route.query.stage_type) {
      this.formData.stage_type = this.$route.query.stage_type;
      // 加载对应的模型列表
      await this.loadAvailableModels(this.formData.stage_type);
    }

    // 如果是编辑模式,加载模板数据
    if (this.isEdit) {
      await this.loadTemplate();
    }
  },
  methods: {
    ...mapActions('prompts', [
      'fetchPromptSets',
      'fetchPromptTemplateDetail',
      'createPromptTemplate',
      'updatePromptTemplate',
      'validateTemplate',
      'previewTemplate',
    ]),

    async loadTemplate() {
      this.loading = true;
      try {
        await this.fetchPromptTemplateDetail(this.$route.params.id);

        if (this.currentTemplate) {
          this.formData = {
            template_set: this.currentTemplate.template_set,
            stage_type: this.currentTemplate.stage_type,
            model_provider: this.currentTemplate.model_provider || '',
            template_content: this.currentTemplate.template_content,
            variables: this.currentTemplate.variables || {},
            is_active: this.currentTemplate.is_active,
          };

          // 转换变量为列表格式
          this.variableList = Object.entries(this.currentTemplate.variables || {}).map(
            ([name, type]) => ({ name, type })
          );

          // 如果有阶段类型,加载对应的模型列表
          if (this.currentTemplate.stage_type) {
            await this.loadAvailableModels(this.currentTemplate.stage_type);
          }
        }
      } catch (error) {
        console.error('加载模板失败:', error);
        this.formError = '加载模板失败,请重试';
      } finally {
        this.loading = false;
      }
    },

    /**
     * 加载可用的AI模型列表
     */
    async loadAvailableModels(stageType) {
      if (!stageType) {
        this.availableModels = [];
        return;
      }

      const providerType = this.stageToProviderType[stageType];
      if (!providerType) {
        console.warn('未知的阶段类型:', stageType);
        this.availableModels = [];
        return;
      }

      this.loadingModels = true;
      try {
        // 使用简化API,仅获取id和name
        const response = await modelProviderApi.getSimpleList({
          provider_type: providerType,
        });

        this.availableModels = response.results || [];
      } catch (error) {
        console.error('加载模型列表失败:', error);
        this.formError = '加载模型列表失败';
        this.availableModels = [];
      } finally {
        this.loadingModels = false;
      }
    },

    /**
     * 处理阶段类型改变
     */
    async handleStageTypeChange() {
      // 清空已选择的模型
      this.formData.model_provider = '';

      // 加载对应的模型列表
      await this.loadAvailableModels(this.formData.stage_type);
    },

    /**
     * 获取模型类型提示
     */
    getModelTypeHint() {
      if (!this.formData.stage_type) {
        return '请先选择阶段类型';
      }

      const providerType = this.stageToProviderType[this.formData.stage_type];
      const typeLabels = {
        llm: 'LLM模型',
        text2image: '文生图模型',
        image2video: '图生视频模型',
      };

      return `当前阶段需要 ${typeLabels[providerType] || providerType} 类型的模型`;
    },

    addVariable() {
      this.variableList.push({ name: '', type: 'string' });
    },

    removeVariable(index) {
      this.variableList.splice(index, 1);
    },

    validateForm() {
      this.errors = {};
      this.formError = '';

      if (!this.formData.template_set) {
        this.errors.template_set = '请选择提示词集';
      }

      if (!this.formData.stage_type) {
        this.errors.stage_type = '请选择阶段类型';
      }

      if (!this.formData.template_content || this.formData.template_content.trim().length === 0) {
        this.errors.template_content = '请输入模板内容';
      }

      // 检查变量定义是否完整
      const hasEmptyVariable = this.variableList.some((v) => !v.name);
      if (hasEmptyVariable) {
        this.errors.variables = '存在未命名的变量';
      }

      // 检查是否有重复的变量名
      const variableNames = this.variableList.map((v) => v.name).filter((n) => n);
      const uniqueNames = new Set(variableNames);
      if (variableNames.length !== uniqueNames.size) {
        this.errors.variables = '存在重复的变量名';
      }

      return Object.keys(this.errors).length === 0 && !this.formError;
    },

    async handleValidate() {
      if (!this.formData.template_content) {
        this.validationResult = {
          valid: false,
          message: '请先输入模板内容',
        };
        return;
      }

      this.validating = true;
      this.validationResult = null;

      try {
        // 创建临时ID用于验证(如果是编辑模式使用真实ID,否则使用0)
        const templateId = this.isEdit ? this.$route.params.id : '0';
        const result = await this.validateTemplate({
          id: templateId,
          templateContent: this.formData.template_content,
        });

        this.validationResult = result;
      } catch (error) {
        console.error('验证失败:', error);
        this.validationResult = {
          valid: false,
          message: error.response?.data?.error || '验证失败',
        };
      } finally {
        this.validating = false;
      }
    },

    handlePreview() {
      this.previewResult = null;
      this.previewError = '';
      this.previewVariables = {};

      // 初始化预览变量
      this.variableList.forEach((variable) => {
        this.previewVariables[variable.name] = '';
      });

      this.$refs.previewDialog.showModal();
    },

    async executePreview() {
      this.previewing = true;
      this.previewError = '';
      this.previewResult = null;

      try {
        // 创建临时ID用于预览(如果是编辑模式使用真实ID,否则使用0)
        const templateId = this.isEdit ? this.$route.params.id : '0';
        const result = await this.previewTemplate({
          id: templateId,
          variables: this.previewVariables,
        });

        this.previewResult = result;
      } catch (error) {
        console.error('预览失败:', error);
        this.previewError = error.response?.data?.error || '预览失败,请检查变量值';
      } finally {
        this.previewing = false;
      }
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
          // 更新模板
          await this.updatePromptTemplate({
            id: this.$route.params.id,
            data: this.formData,
          });
          this.formSuccess = '模板更新成功!';

          // 延迟跳转
          setTimeout(() => {
            this.$router.push(`/prompts/sets/${this.formData.template_set}`);
          }, 1000);
        } else {
          // 创建前检查是否已存在相同的模板
          const existingTemplates = this.promptSets
            .find((set) => set.id === this.formData.template_set)
            ?.templates || [];

          const existingTemplate = existingTemplates.find(
            (t) => t.stage_type === this.formData.stage_type
          );

          if (existingTemplate) {
            const stageLabel = this.stageTypes.find(
              (s) => s.value === this.formData.stage_type
            )?.label || this.formData.stage_type;

            const confirmed = await this.$confirm(
              `该提示词集中已存在 "${stageLabel}" 类型的模板。\n\n创建新模板将替换现有模板。是否继续？`,
              '模板覆盖确认',
              { tone: 'warning', confirmText: '继续创建' }
            );

            if (!confirmed) {
              this.submitting = false;
              return;
            }
          }

          // 创建模板
          await this.createPromptTemplate(this.formData);
          this.formSuccess = '模板创建成功!';

          // 延迟跳转
          setTimeout(() => {
            this.$router.push(`/prompts/sets/${this.formData.template_set}`);
          }, 1000);
        }
      } catch (error) {
        console.error('提交失败:', error);

        if (error.response && error.response.data) {
          const errorData = error.response.data;

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
          this.formError = this.isEdit ? '更新模板失败,请重试' : '创建模板失败,请重试';
        }
      } finally {
        this.submitting = false;
      }
    },

    handleCancel() {
      if (this.formData.template_set) {
        this.$router.push(`/prompts/sets/${this.formData.template_set}`);
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
