<template>
  <div v-if="isVisible" class="modal-overlay" @click="closeModal">
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h3>Конструктор отчетов</h3>
        <button class="close-btn" @click="closeModal">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>

      <div class="modal-body">
        <!-- Выбор формата -->
        <div class="form-group">
          <label class="form-label">Формат файла отчёта</label>
          <div class="format-selector">
            <div
              class="format-option"
              :class="{ 'selected': selectedFormat === 'xlsx' }"
              @click="selectedFormat = 'xlsx'"
            >
              <div class="format-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
                  <path d="M9 9h6v6H9z" fill="currentColor"/>
                  <path d="M9 3v6h6V3" stroke="currentColor" stroke-width="2"/>
                </svg>
              </div>
              <div class="format-info">
                <div class="format-name">Excel</div>
                <div class="format-extension">.xlsx</div>
              </div>
              <div class="format-radio">
                <div class="radio-dot" :class="{ 'active': selectedFormat === 'xlsx' }"></div>
              </div>
            </div>

            <div
              class="format-option"
              :class="{ 'selected': selectedFormat === 'csv' }"
              @click="selectedFormat = 'csv'"
            >
              <div class="format-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
                  <path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
              </div>
              <div class="format-info">
                <div class="format-name">CSV</div>
                <div class="format-extension">.csv</div>
              </div>
              <div class="format-radio">
                <div class="radio-dot" :class="{ 'active': selectedFormat === 'csv' }"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Выбор полей и их порядка -->
        <div class="form-group">
          <label class="form-label">Поля отчёта</label>
          <div class="fields-container">
            <div class="available-fields">
              <h4>Доступные поля</h4>
              <div class="field-list">
                <div
                  v-for="field in availableFields"
                  :key="field.value"
                  class="field-item"
                  :class="{ 'selected': selectedFields.includes(field.value) }"
                  @click="toggleField(field.value)"
                >
                  <span class="field-name">{{ field.label }}</span>
                  <span class="field-value">{{ field.value }}</span>
                </div>
              </div>
            </div>

            <div class="selected-fields">
              <h4>Выбранные поля (порядок)</h4>
              <div class="field-list">
                <div
                  v-for="(field, index) in selectedFields"
                  :key="field"
                  class="field-item selected-field"
                >
                  <span class="field-order">{{ index + 1 }}</span>
                  <span class="field-name">{{ getFieldLabel(field) }}</span>
                  <span class="field-value">{{ field }}</span>
                  <button
                    class="remove-field-btn"
                    @click="removeField(index)"
                    title="Удалить поле"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-secondary" @click="closeModal">Отмена</button>
        <button
          class="btn btn-primary"
          @click="generateReport"
          :disabled="selectedFields.length === 0"
        >
          Сформировать отчет
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

interface Props {
  isVisible: boolean;
  groupUuid: string;
}

interface Emits {
  (e: 'close'): void;
  (e: 'generate', params: { format: string; fields: string[]; groupUuid: string }): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// Доступные поля
const availableFields = ref([
  { value: 'scan_no', label: 'Номер скана' },
  { value: 'fond', label: 'Фонд' },
  { value: 'opis', label: 'Опись' },
  { value: 'delo', label: 'Дело' },
  { value: 'text', label: 'Текст' },
  { value: 'entity_type', label: 'Тип сущности' },
  { value: 'entity_value', label: 'Значение сущности' },
  { value: 'extra', label: 'Дополнительно' }
]);

// Выбранный формат
const selectedFormat = ref('xlsx');

// Выбранные поля
const selectedFields = ref<string[]>([]);

// Получить лейбл поля по значению
const getFieldLabel = (fieldValue: string) => {
  const field = availableFields.value.find(f => f.value === fieldValue);
  return field ? field.label : fieldValue;
};

// Переключить поле (добавить/удалить)
const toggleField = (fieldValue: string) => {
  const index = selectedFields.value.indexOf(fieldValue);
  if (index > -1) {
    selectedFields.value.splice(index, 1);
  } else {
    selectedFields.value.push(fieldValue);
  }
};

// Удалить поле по индексу
const removeField = (index: number) => {
  selectedFields.value.splice(index, 1);
};

// Закрыть модальное окно
const closeModal = () => {
  emit('close');
};

// Сформировать отчет
const generateReport = () => {
  if (selectedFields.value.length === 0) {
    alert('Выберите хотя бы одно поле для отчета');
    return;
  }

  emit('generate', {
    format: selectedFormat.value,
    fields: selectedFields.value,
    groupUuid: props.groupUuid
  });
};
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  max-width: 700px;
  width: 90%;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e0e0e0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  color: #666;
  transition: all 0s ease;
}

.close-btn:hover {
  background-color: #f5f5f5;
  color: #333;
}

.modal-body {
  padding: 24px;
  flex: 1;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 24px;
}

.form-label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #333;
}

.form-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  background: white;
}

.format-selector {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.format-option {
  flex: 1;
  display: flex;
  align-items: center;
  padding: 16px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  background: white;
  position: relative;
}

.format-option:hover {
  border-color: #1976d2;
  box-shadow: 0 2px 8px rgba(25, 118, 210, 0.1);
}

.format-option.selected {
  border-color: #1976d2;
  background-color: #f3f8ff;
  box-shadow: 0 4px 12px rgba(25, 118, 210, 0.15);
}

.format-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background-color: #f5f5f5;
  color: #666;
  margin-right: 12px;
}

.format-icon svg {
  transition: none !important;
}

/* Убираем все transition для SVG элементов */
svg {
  transition: none !important;
}

svg * {
  transition: none !important;
}

.format-option.selected .format-icon {
  background-color: #1976d2;
  color: white;
}

.format-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.format-name {
  font-weight: 600;
  font-size: 14px;
  color: #333;
}

.format-extension {
  font-size: 12px;
  color: #666;
  font-family: monospace;
}

.format-radio {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
}

.radio-dot {
  width: 16px;
  height: 16px;
  border: 2px solid #ddd;
  border-radius: 50%;
  transition: all 0s ease;
  position: relative;
}

.radio-dot.active {
  border-color: #1976d2;
  background-color: #1976d2;
}

.radio-dot.active::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 6px;
  height: 6px;
  background-color: white;
  border-radius: 50%;
}

.fields-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.available-fields h4,
.selected-fields h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.field-list {
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.field-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  transition: all 0s ease;
  border-bottom: 1px solid #f0f0f0;
}

.field-item:last-child {
  border-bottom: none;
}

/* .field-item:hover {
  background-color: #f8f9fa;
} */

.field-item.selected {
  background-color: #e3f2fd;
  color: #1976d2;
}

.selected-field {
  background-color: #e8f5e8;
  cursor: default;
}

.field-order {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background-color: #1976d2;
  color: white;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
  margin-right: 8px;
}

.field-name {
  flex: 1;
  font-weight: 500;
  margin-right: 8px;
}

.field-value {
  font-size: 12px;
  color: #666;
  background-color: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
}

.remove-field-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  border-radius: 3px;
  color: #666;
  margin-left: 8px;
  transition: all 0s ease;
}

.remove-field-btn:hover {
  background-color: #ffdee3;
  color: #d32f2f;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid #e0e0e0;
  background-color: #f8f9fa;
}

.btn {
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0s ease;
  border: none;
}

.btn-secondary {
  background-color: #6c757d;
  color: white;
}

.btn-secondary:hover {
  background-color: #5a6268;
}

.btn-primary {
  background-color: #1976d2;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background-color: #1565c0;
}

.btn-primary:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .fields-container {
    grid-template-columns: 1fr;
  }

  .modal-content {
    width: 95%;
    margin: 20px;
  }

  .format-selector {
    flex-direction: column;
    gap: 8px;
  }

  .format-option {
    padding: 12px;
  }

  .format-icon {
    width: 32px;
    height: 32px;
    margin-right: 8px;
  }
}
</style>
