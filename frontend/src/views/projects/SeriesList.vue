<template>
  <div class="page-shell project-series-list">
    <div class="page-header">
      <div class="page-header-main">
        <h1 class="page-title">作品管理</h1>
        <p class="page-subtitle">{{ seriesList.length }} 个作品</p>
      </div>
      <button class="primary-action" @click="openCreateModal">
        <span>创建作品</span>
      </button>
    </div>

    <LoadingContainer :loading="loading">
      <div v-if="!loading && seriesList.length === 0" class="empty-state">
        <div class="empty-hero">暂无作品</div>
        <p class="empty-hint">创建一个作品后，就可以在作品下持续生产多集内容</p>
        <button class="secondary-action" @click="openCreateModal">创建作品</button>
      </div>

      <div v-else class="card-grid">
        <article
          v-for="series in seriesList"
          :key="series.id"
          class="data-card"
          role="button"
          tabindex="0"
          @click="handleView(series.id)"
          @keyup.enter="handleView(series.id)"
        >
          <div class="card-top">
            <div>
              <h2 class="card-title">{{ series.name }}</h2>
              <p class="card-desc">{{ series.description || '暂无作品描述' }}</p>
            </div>
            <span class="pill">作品</span>
          </div>

          <div class="card-meta">
            <div class="meta-item">
              <span class="meta-label">分集数</span>
              <span class="meta-value">{{ series.episodes_count || 0 }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">已完成</span>
              <span class="meta-value">{{ series.completed_episodes_count || 0 }}</span>
            </div>
          </div>

          <div class="card-footer">
            <span class="meta-time">更新于 {{ formatDate(series.updated_at) }}</span>
            <div class="project-card-actions">
              <button class="project-card-action" @click.stop="openEditModal(series)">编辑</button>
              <button
                class="project-card-action project-card-action--danger"
                :disabled="deletingSeriesId === series.id"
                @click.stop="handleDelete(series)"
              >
                {{ deletingSeriesId === series.id ? '删除中...' : '删除' }}
              </button>
            </div>
          </div>
        </article>
      </div>
    </LoadingContainer>

    <dialog ref="createModal" class="modal">
      <div class="modal-box form-modal-box">
        <h3 class="font-bold text-lg">{{ isEditing ? '编辑作品' : '创建作品' }}</h3>
        <p class="form-hint">作品作为顶层容器，下面可以继续创建多个分集。</p>
        <div class="form-control mt-4">
          <label class="label">
            <span class="label-text">作品名称</span>
          </label>
          <input
            v-model="form.name"
            type="text"
            placeholder="例如：西游记"
            class="input input-bordered w-full"
          >
        </div>
        <div class="form-control mt-4">
          <label class="label">
            <span class="label-text">作品描述</span>
          </label>
          <textarea
            v-model="form.description"
            rows="4"
            placeholder="可选，描述作品定位或创作方向"
            class="textarea textarea-bordered w-full"
          ></textarea>
        </div>
        <div class="modal-action">
          <button class="btn" @click="closeCreateModal">取消</button>
          <button class="btn btn-primary" :disabled="submitting" @click="submitForm">
            {{ submitting ? (isEditing ? '保存中...' : '创建中...') : (isEditing ? '保存' : '创建') }}
          </button>
        </div>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button @click="closeCreateModal">关闭</button>
      </form>
    </dialog>
  </div>
</template>

<script>
import { mapActions, mapState } from 'vuex';
import LoadingContainer from '@/components/common/LoadingContainer.vue';
import { formatDate } from '@/utils/helpers';

export default {
  name: 'SeriesList',
  components: { LoadingContainer },
  data() {
    return {
      loading: false,
      submitting: false,
      deletingSeriesId: null,
      editingSeriesId: null,
      form: {
        name: '',
        description: '',
      },
    };
  },
  computed: {
    ...mapState('projects', ['seriesList']),
    isEditing() {
      return Boolean(this.editingSeriesId);
    },
  },
  created() {
    this.fetchData();
  },
  methods: {
    ...mapActions('projects', ['fetchSeries', 'createSeries', 'updateSeries', 'deleteSeries']),
    formatDate,
    async fetchData() {
      this.loading = true;
      try {
        await this.fetchSeries();
      } finally {
        this.loading = false;
      }
    },
    handleView(id) {
      this.$router.push({ name: 'SeriesDetail', params: { id } });
    },
    openCreateModal() {
      this.editingSeriesId = null;
      this.form = { name: '', description: '' };
      this.$refs.createModal.showModal();
    },
    openEditModal(series) {
      this.editingSeriesId = series.id;
      this.form = {
        name: series.name || '',
        description: series.description || '',
      };
      this.$refs.createModal.showModal();
    },
    closeCreateModal() {
      this.$refs.createModal.close();
      this.editingSeriesId = null;
      this.submitting = false;
      this.form = { name: '', description: '' };
    },
    async submitForm() {
      if (!this.form.name.trim()) {
        await this.$alert('请输入作品名称', '表单校验', { tone: 'warning' });
        return;
      }

      this.submitting = true;
      try {
        if (this.isEditing) {
          await this.updateSeries({
            id: this.editingSeriesId,
            data: {
              name: this.form.name.trim(),
              description: this.form.description.trim(),
            },
          });
          this.$message.success('作品已更新');
        } else {
          const series = await this.createSeries({
            name: this.form.name.trim(),
            description: this.form.description.trim(),
          });
          this.$message.success('作品已创建');
          this.closeCreateModal();
          this.$router.push({ name: 'SeriesDetail', params: { id: series.id } });
          return;
        }

        this.closeCreateModal();
      } catch (error) {
        console.error('Failed to submit series:', error);
        this.$message.error(this.isEditing ? '更新作品失败' : '创建作品失败');
      } finally {
        this.submitting = false;
      }
    },
    async handleDelete(series) {
      const confirmed = await this.$confirm(
        `确定删除作品「${series.name}」吗？其下全部分集也会被删除，此操作不可恢复。`,
        '删除作品',
        { tone: 'danger', confirmText: '删除' }
      );
      if (!confirmed) {
        return;
      }

      this.deletingSeriesId = series.id;
      try {
        await this.deleteSeries(series.id);
        this.$message.success('作品已删除');
      } catch (error) {
        console.error('Failed to delete series:', error);
        this.$message.error('删除作品失败');
      } finally {
        this.deletingSeriesId = null;
      }
    },
  },
};
</script>

<style scoped>
.page-shell {
  min-height: 100%;
  padding: 2.5rem 3.5rem 3rem;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.page-header-main {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.page-title {
  font-size: 2.2rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
  letter-spacing: -0.02em;
}

.layout-shell.theme-dark .page-title {
  color: #e2e8f0;
}

.page-subtitle {
  font-size: 0.95rem;
  color: #64748b;
  margin: 0;
}

.primary-action {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  background: #ffffff;
  color: #0f172a;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 999px;
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.layout-shell.theme-dark .primary-action {
  background: rgba(15, 23, 42, 0.9);
  border-color: rgba(148, 163, 184, 0.25);
  color: #e2e8f0;
}

.primary-action:hover {
  border-color: rgba(20, 184, 166, 0.6);
  box-shadow: 0 12px 24px rgba(20, 184, 166, 0.18);
  transform: translateY(-1px);
}

.layout-shell.theme-dark .primary-action:hover {
  border-color: rgba(94, 234, 212, 0.6);
  box-shadow: 0 12px 24px rgba(2, 6, 23, 0.55);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
}

.data-card {
  background: linear-gradient(90deg, rgba(20, 184, 166, 0.7) 0%, rgba(14, 165, 233, 0.7) 100%)
      0 0 / 0 3px no-repeat,
    rgba(255, 255, 255, 0.92);
  border-radius: 18px;
  padding: 1.5rem;
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  position: relative;
  overflow: visible;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  min-width: 0;
  z-index: 0;
}

.layout-shell.theme-dark .data-card {
  background: linear-gradient(90deg, rgba(94, 234, 212, 0.5) 0%, rgba(56, 189, 248, 0.5) 100%)
      0 0 / 0 3px no-repeat,
    rgba(15, 23, 42, 0.92);
  border-color: rgba(148, 163, 184, 0.2);
  box-shadow: 0 16px 32px rgba(2, 6, 23, 0.55);
}

.data-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 18px 36px rgba(15, 23, 42, 0.12);
  border-color: rgba(148, 163, 184, 0.35);
  background-size: 100% 3px, auto;
  z-index: 5;
}

.layout-shell.theme-dark .data-card:hover {
  box-shadow: 0 18px 36px rgba(2, 6, 23, 0.6);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.card-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
}

.layout-shell.theme-dark .card-title {
  color: #e2e8f0;
}

.card-desc {
  margin: 0.5rem 0 0;
  color: #64748b;
  font-size: 0.9rem;
  line-height: 1.65;
}

.layout-shell.theme-dark .card-desc {
  color: #94a3b8;
}

.pill {
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  background: rgba(20, 184, 166, 0.16);
  color: #0f172a;
}

.layout-shell.theme-dark .pill {
  background: rgba(94, 234, 212, 0.22);
  color: #e2e8f0;
}

.card-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  background: rgba(148, 163, 184, 0.1);
  border-radius: 14px;
  padding: 0.75rem 1rem;
}

.layout-shell.theme-dark .card-meta {
  background: rgba(30, 41, 59, 0.6);
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.meta-label {
  font-size: 0.75rem;
  color: #94a3b8;
}

.meta-value {
  font-size: 0.95rem;
  color: #0f172a;
  font-weight: 600;
}

.layout-shell.theme-dark .meta-value {
  color: #e2e8f0;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.meta-time {
  font-size: 0.8rem;
  color: #94a3b8;
}

.project-card-actions {
  opacity: 0;
  transition: opacity 0.2s ease;
}

.data-card:hover .project-card-actions {
  opacity: 1;
}

.empty-state {
  text-align: center;
  padding: 4rem 1rem;
}

.empty-hero {
  font-size: 1.3rem;
  font-weight: 600;
  color: #0f172a;
}

.layout-shell.theme-dark .empty-hero {
  color: #e2e8f0;
}

.empty-hint {
  color: #94a3b8;
  margin: 0.6rem 0 1.6rem;
}

.secondary-action {
  padding: 0.75rem 1.75rem;
  border-radius: 999px;
  background: #0f172a;
  color: #ffffff;
  border: none;
}

.layout-shell.theme-dark .secondary-action {
  background: #e2e8f0;
  color: #0f172a;
}

.form-modal-box {
  border-radius: 20px;
}

.form-hint {
  margin-top: 0.5rem;
  color: #64748b;
  font-size: 0.9rem;
}

@media (max-width: 768px) {
  .page-shell {
    padding: 2rem 1.5rem;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .primary-action {
    width: 100%;
  }

  .card-footer {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .card-actions {
    opacity: 1;
    flex-wrap: wrap;
  }
}
</style>
