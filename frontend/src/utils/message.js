/**
 * 消息提示工具
 * 简单的消息提示实现,使用daisyUI的alert组件
 */

let messageContainer = null;

function createMessageContainer() {
  if (messageContainer) return messageContainer;

  messageContainer = document.createElement('div');
  messageContainer.id = 'message-container';
  messageContainer.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 400px;
  `;
  document.body.appendChild(messageContainer);
  return messageContainer;
}

function showMessage(message, type = 'info', duration = 3000) {
  const container = createMessageContainer();

  const messageEl = document.createElement('div');
  messageEl.className = `alert alert-${type} shadow-lg`;
  const typeStyleMap = {
    success: `
      background: oklch(var(--p));
      color: oklch(var(--pc));
      border: 1px solid oklch(var(--p));
    `,
  };
  messageEl.style.cssText = `
    animation: slideIn 0.3s ease-out;
    ${typeStyleMap[type] || ''}
  `;

  const iconMap = {
    success: '<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>',
    error: '<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>',
    warning: '<svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>',
    info: '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" class="stroke-current shrink-0 w-6 h-6"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>',
  };

  messageEl.innerHTML = `
    ${iconMap[type] || iconMap.info}
    <span>${message}</span>
  `;

  container.appendChild(messageEl);

  // 自动关闭
  if (duration > 0) {
    setTimeout(() => {
      messageEl.style.animation = 'slideOut 0.3s ease-out';
      setTimeout(() => {
        if (messageEl.parentNode) {
          messageEl.parentNode.removeChild(messageEl);
        }
      }, 300);
    }, duration);
  }

  return messageEl;
}

// 添加动画样式
if (!document.getElementById('message-animation-styles')) {
  const style = document.createElement('style');
  style.id = 'message-animation-styles';
  style.textContent = `
    @keyframes slideIn {
      from {
        transform: translateX(100%);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }

    @keyframes slideOut {
      from {
        transform: translateX(0);
        opacity: 1;
      }
      to {
        transform: translateX(100%);
        opacity: 0;
      }
    }
  `;
  document.head.appendChild(style);
}

export default {
  success(message, duration = 3000) {
    return showMessage(message, 'success', duration);
  },
  error(message, duration = 4000) {
    return showMessage(message, 'error', duration);
  },
  warning(message, duration = 3000) {
    return showMessage(message, 'warning', duration);
  },
  info(message, duration = 3000) {
    return showMessage(message, 'info', duration);
  },
};
