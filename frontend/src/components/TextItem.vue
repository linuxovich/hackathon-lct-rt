<script setup lang="ts">
import { ref, nextTick, watch } from 'vue';

interface Props {
  text: string;
  isHovered: boolean;
  isEditing: boolean;
  isSaving?: boolean;
}

interface Emits {
  (e: 'mouseenter'): void;
  (e: 'mouseleave'): void;
  (e: 'update:text', value: string): void;
  (e: 'start-editing'): void;
  (e: 'cancel-editing'): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const editText = ref('');
const textareaRef = ref<HTMLTextAreaElement>();

const startEditing = () => {
  emit('start-editing');
  editText.value = props.text;
  nextTick(() => {
    textareaRef.value?.focus();
    adjustTextareaHeight();
  });
};

const adjustTextareaHeight = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto';
    textareaRef.value.style.height = textareaRef.value.scrollHeight + 'px';
  }
};

const saveChanges = () => {
  emit('update:text', editText.value);
};

const cancelEditing = () => {
  editText.value = props.text;
  emit('cancel-editing');
};

// Watcher для отслеживания изменения isEditing извне
watch(() => props.isEditing, (newValue) => {
  if (newValue) {
    // Когда редактирование запускается извне (например, при клике на баундинг бокс)
    editText.value = props.text;
    nextTick(() => {
      textareaRef.value?.focus();
      adjustTextareaHeight();
    });
  }
});
</script>

<template>
  <div
    class="text-item"
    :class="{ hovered: isHovered, editing: isEditing }"
    @mouseenter="!isEditing && $emit('mouseenter')"
    @mouseleave="!isEditing && $emit('mouseleave')"
    @click="!isEditing && startEditing()"
  >
    <!-- Режим просмотра -->
    <div v-if="!isEditing" class="text-content">
      <p>{{ text }}</p>
    </div>

    <!-- Режим редактирования -->
    <div v-else class="edit-content">
      <textarea
        ref="textareaRef"
        v-model="editText"
        class="edit-textarea"
        @keydown.enter.ctrl="saveChanges"
        @keydown.escape="cancelEditing"
        @input="adjustTextareaHeight"
      ></textarea>
      <div class="edit-buttons">
        <button
          class="save-btn"
          :class="{ saving: isSaving }"
          :disabled="isSaving"
          @click.stop="saveChanges"
          title="Сохранить (Ctrl+Enter)"
        >
          <span v-if="!isSaving">Сохранить</span>
          <span v-else class="saving-text">
            <span class="saving-spinner"></span>
            Сохранение...
          </span>
        </button>
        <button class="cancel-btn" @click.stop="cancelEditing" title="Отменить (Esc)">
          Отменить
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.text-item {
  padding: 12px 16px;
  background: #f8f9fa;
  border: 2px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;

  &:hover,
  &.hovered {
    background: #e3f2fd;
    border-color: #2196f3;
  }

  &.editing {
    background: #ffffff;
    border-color: #2196f3;
    cursor: default;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
}

.text-content {
  p {
    margin: 0;
    line-height: 1.4;
  }
}

.edit-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edit-textarea {
  width: 100%;
  min-height: calc(16px * 1.4);
  border: none;
  border-radius: 6px;
  font-family: inherit;
  font-size: 16px;
  line-height: 1.4;
  resize: vertical;
  outline: none;
  background: transparent;
  color: inherit;
  overflow: hidden;

  &:focus {
    outline: none;
  }
}

.edit-buttons {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 4px;
}

.save-btn,
.cancel-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 100px;
}

.save-btn {
  background: linear-gradient(135deg, #4caf50, #45a049);
  color: white;
  box-shadow: 0 2px 4px rgba(76, 175, 80, 0.3);

  &:hover:not(:disabled) {
    background: linear-gradient(135deg, #45a049, #3d8b40);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(76, 175, 80, 0.4);
  }

  &:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(76, 175, 80, 0.3);
  }

  &.saving {
    background: linear-gradient(135deg, #9e9e9e, #757575);
    cursor: not-allowed;
    opacity: 0.8;
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.8;
  }
}

.saving-text {
  display: flex;
  align-items: center;
  gap: 8px;
}

.saving-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top: 2px solid white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.cancel-btn {
  background: linear-gradient(135deg, #f44336, #d32f2f);
  color: white;
  box-shadow: 0 2px 4px rgba(244, 67, 54, 0.3);

  &:hover {
    background: linear-gradient(135deg, #d32f2f, #b71c1c);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(244, 67, 54, 0.4);
  }

  &:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(244, 67, 54, 0.3);
  }
}
</style>
