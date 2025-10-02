<script setup lang="ts">
import { ref, nextTick } from 'vue';

interface Props {
  text: string;
  isHovered: boolean;
  isEditing: boolean;
  documentStatus?: string;
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
  // Блокируем редактирование если статус документа не 'done'
  if (props.documentStatus && props.documentStatus !== 'done') {
    return;
  }

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
  console.log('TextItem: saveChanges вызвана, новый текст:', editText.value);
  console.log('TextItem: editText.value:', editText.value);
  console.log('TextItem: props.text:', props.text);
  emit('update:text', editText.value);
  console.log('TextItem: событие update:text отправлено');
};

const cancelEditing = () => {
  editText.value = props.text;
  emit('cancel-editing');
};
</script>

<template>
  <div
    class="text-item"
    :class="{
      hovered: isHovered,
      editing: isEditing,
      disabled: documentStatus && documentStatus !== 'done',
    }"
    @mouseenter="!isEditing && $emit('mouseenter')"
    @mouseleave="!isEditing && $emit('mouseleave')"
    @click="!isEditing && (documentStatus === 'done' || !documentStatus) && startEditing()"
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
        @keydown.enter.ctrl="
          () => {
            console.log('Ctrl+Enter нажато!');
            saveChanges();
          }
        "
        @keydown.escape="cancelEditing"
        @input="adjustTextareaHeight"
      ></textarea>
      <div class="edit-buttons">
        <button
          class="save-btn"
          @click.stop="
            () => {
              console.log('Кнопка Сохранить нажата!');
              saveChanges();
            }
          "
          title="Сохранить (Ctrl+Enter)"
        >
          Сохранить
        </button>
        <button
          class="cancel-btn"
          @click.stop="
            () => {
              console.log('Кнопка Отменить нажата!');
              cancelEditing();
            }
          "
          title="Отменить (Esc)"
        >
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

  &.disabled {
    cursor: not-allowed;
    opacity: 0.6;
    background: #f5f5f5;

    &:hover {
      background: #f5f5f5;
      border-color: transparent;
    }
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

  &:hover {
    background: linear-gradient(135deg, #45a049, #3d8b40);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(76, 175, 80, 0.4);
  }

  &:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(76, 175, 80, 0.3);
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
