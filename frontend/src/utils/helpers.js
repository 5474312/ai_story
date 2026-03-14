/**
 * 格式化日期时间
 * @param {Date|string} date - 日期对象或字符串
 * @param {string} format - 格式化模板
 * @returns {string}
 */
export function formatDate(date, format = 'YYYY-MM-DD HH:mm:ss') {
  if (!date) return '';

  const d = new Date(date);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  const seconds = String(d.getSeconds()).padStart(2, '0');

  return format
    .replace('YYYY', year)
    .replace('MM', month)
    .replace('DD', day)
    .replace('HH', hours)
    .replace('mm', minutes)
    .replace('ss', seconds);
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string}
 */
export function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 B';

  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

/**
 * 格式化持续时间
 * @param {number} seconds - 秒数
 * @returns {string}
 */
export function formatDuration(seconds) {
  if (!seconds || seconds === 0) return '0秒';

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  const parts = [];
  if (hours > 0) parts.push(`${hours}小时`);
  if (minutes > 0) parts.push(`${minutes}分`);
  if (secs > 0) parts.push(`${secs}秒`);

  return parts.join('');
}

/**
 * 防抖函数
 * @param {Function} func - 要执行的函数
 * @param {number} wait - 等待时间(毫秒)
 * @returns {Function}
 */
export function debounce(func, wait = 300) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * 节流函数
 * @param {Function} func - 要执行的函数
 * @param {number} limit - 时间限制(毫秒)
 * @returns {Function}
 */
export function throttle(func, limit = 300) {
  let inThrottle;
  return function executedFunction(...args) {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

/**
 * 深拷贝对象
 * @param {any} obj - 要拷贝的对象
 * @returns {any}
 */
export function deepClone(obj) {
  if (obj === null || typeof obj !== 'object') return obj;
  if (obj instanceof Date) return new Date(obj.getTime());
  if (obj instanceof Array) return obj.map((item) => deepClone(item));

  const clonedObj = {};
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      clonedObj[key] = deepClone(obj[key]);
    }
  }
  return clonedObj;
}

/**
 * 获取项目状态标签
 * @param {string} status - 状态值
 * @returns {object}
 */
export function getProjectStatusTag(status) {
  const statusMap = {
    draft: { label: '草稿', type: 'info' },
    processing: { label: '处理中', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    failed: { label: '失败', type: 'danger' },
    paused: { label: '已暂停', type: '' },
  };
  return statusMap[status] || { label: status, type: 'info' };
}

/**
 * 获取阶段状态标签
 * @param {string} status - 状态值
 * @returns {object}
 */
export function getStageStatusTag(status) {
  const statusMap = {
    pending: { label: '待执行', type: 'info' },
    running: { label: '执行中', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    failed: { label: '失败', type: 'danger' },
    skipped: { label: '已跳过', type: '' },
  };
  return statusMap[status] || { label: status, type: 'info' };
}
