<script setup lang="ts">
import { ref, computed, nextTick } from 'vue';

import { useDocumentsStore, useFileStore } from '@/stores/documents';
import { onMounted, onBeforeUnmount, watch } from 'vue';
import { DocumentStatusesEnum, type Document } from '@/interfaces/documents';
import { API_ROUTES, client, uploadClient } from '@/constants';
import IconPlus from '@/icons/IconPlus.vue';
import ReportConstructor from './ReportConstructor.vue';

const timer = ref();

const documentsStore = useDocumentsStore();
const fileStore = useFileStore();

// Computed свойства для статистики документов
const totalDocuments = computed(() => {
  const total = documentsStore.all.reduce((total, group) => total + group.length, 0);
  if (import.meta.env.DEV) {
    console.log('Total documents:', total, 'Groups:', documentsStore.all.length);
  }
  return total;
});

const processingDocuments = computed(() => {
  const processing = documentsStore.all.reduce((total, group) => {
    return (
      total +
      group.filter(
        (doc) =>
          doc.status === DocumentStatusesEnum.progress ||
          doc.status === DocumentStatusesEnum.upgrading,
      ).length
    );
  }, 0);
  if (import.meta.env.DEV) {
    console.log('Processing documents:', processing);
  }
  return processing;
});

const completedDocuments = computed(() => {
  const completed = documentsStore.all.reduce((total, group) => {
    return total + group.filter((doc) => doc.status === DocumentStatusesEnum.done).length;
  }, 0);
  if (import.meta.env.DEV) {
    console.log('Completed documents:', completed);

    // Детальная отладочная информация
    documentsStore.all.forEach((group, groupIndex) => {
      console.log(
        `Group ${groupIndex}:`,
        group.map((doc) => ({
          filename: doc.filename,
          status: doc.status,
        })),
      );
    });
  }

  return completed;
});

// Отладочная информация
console.log('documentsStore methods:', Object.keys(documentsStore));
console.log('uploadZipFile exists:', 'uploadZipFile' in documentsStore);
console.log('Store type:', typeof documentsStore);
console.log('Store constructor:', documentsStore.constructor?.name);

// Состояние сворачивания групп
const collapsedGroups = ref<boolean[]>([]);

// Состояние для тултипов
const showDownloadTooltip = ref<number | null>(null);
const showCollapseTooltip = ref<number | null>(null);
const showDeleteTooltip = ref<number | null>(null);
const showAddFilesTooltip = ref<number | null>(null);
const showFundTooltip = ref<number | null>(null);
const showInventoryTooltip = ref<number | null>(null);
const showCaseTooltip = ref<number | null>(null);

// Состояние для редактирования
const editingState = ref<{
  groupIndex: number | null;
  field: 'fond' | 'opis' | 'delo' | null;
  value: string;
}>({
  groupIndex: null,
  field: null,
  value: '',
});

// Состояние для конструктора отчетов
const showReportConstructor = ref(false);
const selectedGroupUuid = ref<string>('');

const editValues = ref<
  Record<
    string,
    {
      fond: string;
      opis: string;
      delo: string;
    }
  >
>({});

// Computed для placeholder
const editPlaceholder = computed(() => {
  if (editingState.value.field === 'fond') return 'Фонд';
  if (editingState.value.field === 'opis') return 'Опись';
  if (editingState.value.field === 'delo') return 'Дело';
  return '';
});

// Состояние для подтверждения удаления
const showDeleteConfirmation = ref(false);
const groupToDelete = ref<number | null>(null);

// Состояние для загрузки файлов в группы
const groupUploadingStates = ref<boolean[]>([]);
const groupUploadProgress = ref<number[]>([]);

// Функции для работы с localStorage
function saveCollapsedGroups() {
  localStorage.setItem('collapsed_groups', JSON.stringify(collapsedGroups.value));
}

function loadCollapsedGroups() {
  const stored = localStorage.getItem('collapsed_groups');
  if (stored) {
    collapsedGroups.value = JSON.parse(stored);
  }
}

// Состояние для drag&drop
const isDragOver = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);

// Обработчик клика на файл
const handleFileClick = (file: Document) => {
  if (file.status === DocumentStatusesEnum.done || file.status === DocumentStatusesEnum.upgrading) {
    fileStore.setSelectedFile(file.file_uuid);
    // Отправляем запрос с соответствующим stage в зависимости от статуса документа
    const stage = file.status === DocumentStatusesEnum.upgrading ? 'upgrading' : 'done';
    fileStore.fetchFileContent(file.file_uuid, stage);
  }
};

// Обработчик сворачивания/разворачивания группы
const toggleGroupCollapse = (groupIndex: number) => {
  collapsedGroups.value[groupIndex] = !collapsedGroups.value[groupIndex];
  saveCollapsedGroups();
};

// Функции для управления тултипами
const showTooltip = (groupIndex: number) => {
  showDownloadTooltip.value = groupIndex;
};

const hideTooltip = () => {
  showDownloadTooltip.value = null;
};

const showCollapseTooltipHandler = (groupIndex: number) => {
  showCollapseTooltip.value = groupIndex;
};

const hideCollapseTooltip = () => {
  showCollapseTooltip.value = null;
};

const showDeleteTooltipHandler = (groupIndex: number) => {
  showDeleteTooltip.value = groupIndex;
};

const hideDeleteTooltip = () => {
  showDeleteTooltip.value = null;
};

const showAddFilesTooltipHandler = (groupIndex: number) => {
  showAddFilesTooltip.value = groupIndex;
};

const hideAddFilesTooltip = () => {
  showAddFilesTooltip.value = null;
};

const showFundTooltipHandler = (groupIndex: number) => {
  showFundTooltip.value = groupIndex;
};

const hideFundTooltip = () => {
  showFundTooltip.value = null;
};

const showInventoryTooltipHandler = (groupIndex: number) => {
  showInventoryTooltip.value = groupIndex;
};

const hideInventoryTooltip = () => {
  showInventoryTooltip.value = null;
};

const showCaseTooltipHandler = (groupIndex: number) => {
  showCaseTooltip.value = groupIndex;
};

const hideCaseTooltip = () => {
  showCaseTooltip.value = null;
};

// Обработчики редактирования
const startEditing = (groupIndex: number, field: 'fond' | 'opis' | 'delo') => {
  const groupUuid = documentsStore.groupUuids[groupIndex];
  if (!groupUuid) return;

  // Инициализируем значения для группы, если их еще нет
  if (!editValues.value[groupUuid]) {
    editValues.value[groupUuid] = {
      fond: '',
      opis: '',
      delo: '',
    };
  }

  editingState.value = {
    groupIndex,
    field,
    value: editValues.value[groupUuid][field],
  };

  // Фокусируемся на input после следующего рендера
  nextTick(() => {
    const editInput = document.querySelector('.edit-input') as HTMLInputElement;
    if (editInput) {
      editInput.focus();
      editInput.select();
    }
  });
};

const cancelEditing = () => {
  editingState.value = {
    groupIndex: null,
    field: null,
    value: '',
  };

  // Очищаем все тултипы при выходе из режима редактирования
  showFundTooltip.value = null;
  showInventoryTooltip.value = null;
  showCaseTooltip.value = null;
};

const saveEditing = async () => {
  if (editingState.value.groupIndex === null || editingState.value.field === null) return;

  try {
    const groupUuid = documentsStore.groupUuids[editingState.value.groupIndex];
    if (!groupUuid) {
      console.error('Group UUID не найден');
      return;
    }

    // Обновляем значение в локальном состоянии для конкретной группы
    editValues.value[groupUuid][editingState.value.field] = editingState.value.value;

    // Получаем текущие значения для отправки (включая только что обновленное)
    const currentValues = editValues.value[groupUuid];

    // Отправляем PATCH запрос
    const response = await client.patch(`/api/v1/groups/${groupUuid}`, {
      fond: currentValues.fond,
      opis: currentValues.opis,
      delo: currentValues.delo,
    });

    console.log('Группа успешно обновлена:', response.data);

    // Закрываем режим редактирования
    cancelEditing();
  } catch (error) {
    console.error('Ошибка при сохранении группы:', error);
    alert('Ошибка при сохранении. Попробуйте еще раз.');
  }
};

// Функция для получения данных групп
const fetchGroupsData = async () => {
  try {
    // Получаем все group_uuid из store
    const groupUuids = documentsStore.groupUuids;

    // Запрашиваем данные для каждой группы
    for (const groupUuid of groupUuids) {
      if (!groupUuid) continue;

      try {
        const response = await client.get(`/api/v1/groups/${groupUuid}`);
        const groupData = response.data;

        // Обновляем значения в editValues
        if (
          groupData.fond !== undefined ||
          groupData.opis !== undefined ||
          groupData.delo !== undefined
        ) {
          if (!editValues.value[groupUuid]) {
            editValues.value[groupUuid] = {
              fond: '',
              opis: '',
              delo: '',
            };
          }

          if (groupData.fond !== undefined) {
            editValues.value[groupUuid].fond = groupData.fond;
          }
          if (groupData.opis !== undefined) {
            editValues.value[groupUuid].opis = groupData.opis;
          }
          if (groupData.delo !== undefined) {
            editValues.value[groupUuid].delo = groupData.delo;
          }
        }
      } catch (error) {
        console.error(`Ошибка при получении данных группы ${groupUuid}:`, error);
        // Продолжаем с другими группами даже если одна не удалась
      }
    }
  } catch (error) {
    console.error('Ошибка при получении данных групп:', error);
  }
};

// Функция для проверки, все ли файлы в группе находятся в статусе done
const isGroupReadyForReport = (groupIndex: number): boolean => {
  const groupDocuments = documentsStore.all[groupIndex];
  if (!groupDocuments || groupDocuments.length === 0) {
    return false;
  }

  return groupDocuments.every((file) => file.status === DocumentStatusesEnum.done);
};

// Функция для показа подтверждения удаления
const showDeleteConfirmationDialog = (groupIndex: number) => {
  groupToDelete.value = groupIndex;
  showDeleteConfirmation.value = true;
};

// Функция для подтверждения удаления группы
const confirmDeleteGroup = () => {
  if (groupToDelete.value !== null) {
    // Проверяем, есть ли выбранный файл в удаляемой группе
    const selectedFileUuid = fileStore.selectedFileUuid;
    if (selectedFileUuid) {
      const groupToDeleteIndex = groupToDelete.value;
      const groupDocuments = documentsStore.all[groupToDeleteIndex];

      // Проверяем, есть ли выбранный файл в удаляемой группе
      const isSelectedFileInDeletedGroup = groupDocuments?.some(
        (doc) => doc.file_uuid === selectedFileUuid,
      );

      if (isSelectedFileInDeletedGroup) {
        // Очищаем выбранный файл, если он принадлежит удаляемой группе
        fileStore.clearSelectedFile();
      }
    }

    // Удаляем группу из store
    documentsStore.removeGroup(groupToDelete.value);

    // Обновляем состояние сворачивания групп
    collapsedGroups.value.splice(groupToDelete.value, 1);
    saveCollapsedGroups();
  }

  // Закрываем модальное окно
  showDeleteConfirmation.value = false;
  groupToDelete.value = null;
};

// Функция для отмены удаления
const cancelDeleteGroup = () => {
  showDeleteConfirmation.value = false;
  groupToDelete.value = null;
};

// Функция для открытия конструктора отчетов для группы
const openReportConstructor = (groupUuid: string) => {
  selectedGroupUuid.value = groupUuid;
  showReportConstructor.value = true;
};

// Функция для открытия конструктора отчетов для файла
const openFileReportConstructor = (fileUuid: string) => {
  selectedGroupUuid.value = fileUuid;
  showReportConstructor.value = true;
};

// Функция для закрытия конструктора отчетов
const closeReportConstructor = () => {
  showReportConstructor.value = false;
  selectedGroupUuid.value = '';
};

// Функция для скачивания отчета с параметрами (для групп и файлов)
const downloadReportWithParams = async (uuid: string, format: string, fields: string[], isFile: boolean = false) => {
  try {
    // Формируем URL с параметрами
    const fieldsParam = fields.join(',');
    let baseUrl: string;

    if (isFile) {
      // Для файлов используем эндпоинт файлов
      baseUrl = API_ROUTES.files.report(uuid);
    } else {
      // Для групп используем эндпоинт групп
      baseUrl = API_ROUTES.groups.report(uuid);
    }

    const url = `${baseUrl}?format=${format}&stage=done&fields=${encodeURIComponent(fieldsParam)}`;

    const response = await client.get(url, {
      responseType: 'blob',
    });

    // Определяем расширение файла из Content-Type заголовка
    const contentType = response.headers['content-type'] || '';
    let fileExtension = format === 'csv' ? '.csv' : '.xlsx'; // По умолчанию

    if (contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
      fileExtension = '.xlsx';
    } else if (contentType.includes('application/pdf')) {
      fileExtension = '.pdf';
    } else if (contentType.includes('application/vnd.ms-excel')) {
      fileExtension = '.xls';
    } else if (contentType.includes('text/csv')) {
      fileExtension = '.csv';
    }

    // Создаем URL для blob
    const blob = new Blob([response.data], { type: contentType });
    const urlObject = window.URL.createObjectURL(blob);

    // Создаем временную ссылку для скачивания
    const link = document.createElement('a');
    link.href = urlObject;
    link.download = `report_${uuid}${fileExtension}`;
    document.body.appendChild(link);
    link.click();

    // Очищаем ресурсы
    document.body.removeChild(link);
    window.URL.revokeObjectURL(urlObject);

    // Закрываем конструктор
    closeReportConstructor();
  } catch (error) {
    console.error('Ошибка при скачивании отчета:', error);
    alert('Ошибка при скачивании отчета. Попробуйте еще раз.');
  }
};

// Функция для обработки генерации отчета из конструктора
const handleGenerateReport = (params: { format: string; fields: string[]; groupUuid: string }) => {
  // Определяем, является ли UUID файлом или группой
  const isFile = documentsStore.all.some(group =>
    group.some(file => file.file_uuid === params.groupUuid)
  );

  downloadReportWithParams(params.groupUuid, params.format, params.fields, isFile);
};

// Функция для загрузки файлов в существующую группу
const handleAddFilesToGroup = async (groupIndex: number) => {
  const groupUuid = documentsStore.groupUuids[groupIndex];
  if (!groupUuid) {
    console.error('Group UUID не найден для группы', groupIndex);
    return;
  }

  // Создаем скрытый input для выбора файлов
  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = true;
  input.accept = '.jpg,.jpeg,.png,.bmp,.webp,image/jpeg,image/jpg,image/png,image/bmp,image/webp';
  input.style.display = 'none';

  input.onchange = async (event) => {
    const target = event.target as HTMLInputElement;
    const files = target.files;
    if (files && files.length > 0) {
      const imageFiles = Array.from(files).filter((file) => {
        const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/bmp', 'image/webp'];
        const validExtensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp'];
        return (
          validTypes.includes(file.type) ||
          validExtensions.some((ext) => file.name.toLowerCase().endsWith(ext))
        );
      });

      if (imageFiles.length > 0) {
        await uploadFilesToGroup(imageFiles, groupUuid, groupIndex);
      } else {
        alert('Пожалуйста, выберите изображения в форматах JPG, JPEG, PNG, BMP или WEBP');
      }
    }
  };

  document.body.appendChild(input);
  input.click();
  document.body.removeChild(input);
};

// Функция загрузки файлов в группу
const uploadFilesToGroup = async (files: File[], groupUuid: string, groupIndex: number) => {
  try {
    console.log('=== НАЧАЛО ЗАГРУЗКИ ФАЙЛОВ В ГРУППУ ===');
    console.log('Group UUID:', groupUuid);
    console.log('Group Index:', groupIndex);
    console.log(
      'Файлы:',
      files.map((f) => ({ name: f.name, size: f.size, type: f.type })),
    );

    // Устанавливаем состояние загрузки для конкретной группы
    groupUploadingStates.value[groupIndex] = true;
    groupUploadProgress.value[groupIndex] = 0;

    // Используем uploadClient из constants

    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    console.log('Отправляем запрос на:', API_ROUTES.upload.filesToGroup(groupUuid));

    const response = await uploadClient.post(API_ROUTES.upload.filesToGroup(groupUuid), formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          groupUploadProgress.value[groupIndex] = percentCompleted;
          console.log(`Прогресс загрузки группы ${groupIndex}: ${percentCompleted}%`);
        }
      },
    });

    console.log('Ответ сервера:', response.data);
    console.log('Статус:', response.status);

    // Обновляем список документов после успешной загрузки
    console.log('Обновляем список документов...');
    await documentsStore.fetchAllDocuments();
    console.log('=== КОНЕЦ ЗАГРУЗКИ ФАЙЛОВ В ГРУППУ ===');
  } catch (error) {
    console.error('=== ОШИБКА ЗАГРУЗКИ ФАЙЛОВ В ГРУППУ ===');
    console.error('Ошибка:', error);
    const errorMessage = error instanceof Error ? error.message : 'Неизвестная ошибка';
    alert(`Ошибка загрузки файлов в группу: ${errorMessage}`);
  } finally {
    // Сбрасываем состояние загрузки для группы
    groupUploadingStates.value[groupIndex] = false;
    groupUploadProgress.value[groupIndex] = 0;
  }
};

// Обработчики drag&drop
const handleDragOver = (event: DragEvent) => {
  event.preventDefault();
  isDragOver.value = true;
};

const handleDragLeave = (event: DragEvent) => {
  event.preventDefault();
  isDragOver.value = false;
};

const handleDrop = async (event: DragEvent) => {
  event.preventDefault();
  isDragOver.value = false;

  const files = event.dataTransfer?.files;
  if (files && files.length > 0) {
    const imageFiles = Array.from(files).filter((file) => {
      const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/bmp', 'image/webp'];
      const validExtensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp'];
      return (
        validTypes.includes(file.type) ||
        validExtensions.some((ext) => file.name.toLowerCase().endsWith(ext))
      );
    });

    if (imageFiles.length > 0) {
      await handleFileUpload(imageFiles);
    } else {
      alert('Пожалуйста, загрузите изображения в форматах JPG, JPEG, PNG, BMP или WEBP');
    }
  }
};

// Обработчик клика на drop-zone для выбора файла
const handleDropZoneClick = () => {
  fileInputRef.value?.click();
};

// Обработчик выбора файлов через input
const handleFileInputChange = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  const files = target.files;
  if (files && files.length > 0) {
    const imageFiles = Array.from(files).filter((file) => {
      const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/bmp', 'image/webp'];
      const validExtensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp'];
      return (
        validTypes.includes(file.type) ||
        validExtensions.some((ext) => file.name.toLowerCase().endsWith(ext))
      );
    });

    if (imageFiles.length > 0) {
      await handleFileUpload(imageFiles);
    } else {
      alert('Пожалуйста, выберите изображения в форматах JPG, JPEG, PNG, BMP или WEBP');
    }
  }
  // Очищаем input для возможности повторного выбора тех же файлов
  target.value = '';
};

// Функция загрузки файлов
const handleFileUpload = async (files: File[]) => {
  try {
    console.log('=== НАЧАЛО ЗАГРУЗКИ ФАЙЛОВ ===');
    console.log(
      'Файлы:',
      files.map((f) => ({ name: f.name, size: f.size, type: f.type })),
    );
    console.log('documentsStore:', documentsStore);
    console.log('uploadFiles method:', documentsStore.uploadFiles);
    console.log('API_BASE:', API_ROUTES.upload.files());

    if (typeof documentsStore.uploadFiles !== 'function') {
      console.error(
        'uploadFiles is not a function, available methods:',
        Object.keys(documentsStore),
      );
      throw new Error('uploadFiles is not a function');
    }

    console.log('Вызываем uploadFiles...');
    // Загружаем файлы сразу с "none" для всех полей
    await documentsStore.uploadFiles(files);
    console.log('Файлы успешно загружены');
    console.log('=== КОНЕЦ ЗАГРУЗКИ ФАЙЛОВ ===');
  } catch (error) {
    console.error('=== ОШИБКА ЗАГРУЗКИ ФАЙЛОВ ===');
    console.error('Ошибка:', error);
    console.error('Тип ошибки:', typeof error);
    const errorMessage = error instanceof Error ? error.message : 'Неизвестная ошибка';
    const errorStack = error instanceof Error ? error.stack : undefined;
    console.error('Сообщение:', errorMessage);
    console.error('Стек:', errorStack);
    alert(`Ошибка загрузки файлов: ${errorMessage}`);
  }
};

// Watcher для отслеживания изменений в группах и очистки выбранного файла
watch(
  () => documentsStore.all,
  (newAll) => {
    const selectedFileUuid = fileStore.selectedFileUuid;
    if (selectedFileUuid) {
      // Проверяем, существует ли выбранный файл в любой из групп
      const fileExists = newAll.some((group) =>
        group.some((doc) => doc.file_uuid === selectedFileUuid),
      );

      if (!fileExists) {
        // Если файл больше не существует, очищаем выбор
        console.log('Выбранный файл больше не существует, очищаем выбор');
        fileStore.clearSelectedFile();
      }
    }
  },
  { deep: true },
);

onMounted(async () => {
  // Проверяем, что store правильно инициализирован
  console.log('Store on mount:', documentsStore);
  console.log('Available methods:', Object.getOwnPropertyNames(documentsStore));

  documentsStore.fetchAllDocuments();
  await fetchGroupsData();

  // Инициализируем состояние сворачивания для всех групп
  watch(
    () => documentsStore.all,
    (newAll) => {
      // Загружаем сохраненное состояние
      loadCollapsedGroups();

      // Если количество групп изменилось, расширяем или обрезаем массив
      const currentLength = collapsedGroups.value.length;
      const newLength = newAll.length;

      if (newLength > currentLength) {
        // Добавляем новые группы (по умолчанию развернуты)
        for (let i = currentLength; i < newLength; i++) {
          collapsedGroups.value[i] = false;
        }
      } else if (newLength < currentLength) {
        // Удаляем лишние группы
        collapsedGroups.value = collapsedGroups.value.slice(0, newLength);
      }

      // Инициализируем состояние загрузки для групп
      groupUploadingStates.value = new Array(newLength).fill(false);
      groupUploadProgress.value = new Array(newLength).fill(0);

      // Сохраняем обновленное состояние
      saveCollapsedGroups();
    },
    { immediate: true },
  );

  timer.value = setInterval(async () => {
    documentsStore.fetchAllDocuments();
    await fetchGroupsData();
  }, 10000);
});

onBeforeUnmount(() => {
  timer.value = null;
});
</script>

<template>
  <div class="menu-wrapper">
    <!-- Статистика документов -->
    <div class="stats-section">
      <div class="stats-item">
        <div class="stats-icon total">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path
              d="M14 2V8H20"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path
              d="M16 13H8"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path
              d="M16 17H8"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path
              d="M10 9H8"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </div>
        <div class="stats-info">
          <div class="stats-number">{{ totalDocuments }}</div>
          <div class="stats-label">Всего</div>
        </div>
      </div>

      <div class="stats-item">
        <div class="stats-icon processing">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" />
            <path
              d="M12 6V12L16 14"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </div>
        <div class="stats-info">
          <div class="stats-number">{{ processingDocuments }}</div>
          <div class="stats-label">В обработке</div>
        </div>
      </div>

      <div class="stats-item">
        <div class="stats-icon completed">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M9 12L11 14L15 10"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" />
          </svg>
        </div>
        <div class="stats-info">
          <div class="stats-number">{{ completedDocuments }}</div>
          <div class="stats-label">Готово</div>
        </div>
      </div>
    </div>

    <!-- Верхняя часть - группы документов -->
    <div class="documents-section">
      <!-- <h3 class="section-title">Документы</h3> -->

      <div class="groups-list">
        <div
          v-for="(groupDocuments, groupIndex) in documentsStore.all"
          :key="`group-${groupIndex}`"
          class="group-item"
        >
          <div class="group-header">
            <div class="group-name-section">
              <div class="group-headers">
                <div
                  class="group-header-item-wrapper"
                  @mouseenter="showFundTooltipHandler(groupIndex)"
                  @mouseleave="hideFundTooltip()"
                >
                  <div
                    v-if="editingState.groupIndex !== groupIndex || editingState.field !== 'fond'"
                    class="group-header-item"
                    @click="startEditing(groupIndex, 'fond')"
                  >
                    {{ editValues[documentsStore.groupUuids[groupIndex]]?.fond || '???' }}
                  </div>
                  <div v-else class="edit-container">
                    <input
                      v-model="editingState.value"
                      class="edit-input"
                      :placeholder="editPlaceholder"
                      @keyup.enter="saveEditing"
                      @keyup.escape="cancelEditing"
                      ref="editInput"
                    />
                    <div class="edit-actions">
                      <button class="edit-save-btn" @click="saveEditing">
                        <div class="edit-save-icon"></div>
                      </button>
                      <button class="edit-cancel-btn" @click="cancelEditing">
                        <div class="edit-cancel-icon"></div>
                      </button>
                    </div>
                  </div>
                  <div
                    v-if="
                      showFundTooltip === groupIndex &&
                      !(editingState.groupIndex === groupIndex && editingState.field === 'fond')
                    "
                    class="header-tooltip"
                    :class="{ 'tooltip-bottom': groupIndex === 0 }"
                  >
                    Фонд
                  </div>
                </div>
                <div
                  class="group-header-item-wrapper"
                  @mouseenter="showInventoryTooltipHandler(groupIndex)"
                  @mouseleave="hideInventoryTooltip()"
                >
                  <div
                    v-if="editingState.groupIndex !== groupIndex || editingState.field !== 'opis'"
                    class="group-header-item"
                    @click="startEditing(groupIndex, 'opis')"
                  >
                    {{ editValues[documentsStore.groupUuids[groupIndex]]?.opis || '???' }}
                  </div>
                  <div v-else class="edit-container">
                    <input
                      v-model="editingState.value"
                      class="edit-input"
                      :placeholder="editPlaceholder"
                      @keyup.enter="saveEditing"
                      @keyup.escape="cancelEditing"
                      ref="editInput"
                    />
                    <div class="edit-actions">
                      <button class="edit-save-btn" @click="saveEditing">
                        <div class="edit-save-icon"></div>
                      </button>
                      <button class="edit-cancel-btn" @click="cancelEditing">
                        <div class="edit-cancel-icon"></div>
                      </button>
                    </div>
                  </div>
                  <div
                    v-if="
                      showInventoryTooltip === groupIndex &&
                      !(editingState.groupIndex === groupIndex && editingState.field === 'opis')
                    "
                    class="header-tooltip"
                    :class="{ 'tooltip-bottom': groupIndex === 0 }"
                  >
                    Опись
                  </div>
                </div>
                <div
                  class="group-header-item-wrapper"
                  @mouseenter="showCaseTooltipHandler(groupIndex)"
                  @mouseleave="hideCaseTooltip()"
                >
                  <div
                    v-if="editingState.groupIndex !== groupIndex || editingState.field !== 'delo'"
                    class="group-header-item"
                    @click="startEditing(groupIndex, 'delo')"
                  >
                    {{ editValues[documentsStore.groupUuids[groupIndex]]?.delo || '???' }}
                  </div>
                  <div v-else class="edit-container">
                    <input
                      v-model="editingState.value"
                      class="edit-input"
                      :placeholder="editPlaceholder"
                      @keyup.enter="saveEditing"
                      @keyup.escape="cancelEditing"
                      ref="editInput"
                    />
                    <div class="edit-actions">
                      <button class="edit-save-btn" @click="saveEditing">
                        <div class="edit-save-icon"></div>
                      </button>
                      <button class="edit-cancel-btn" @click="cancelEditing">
                        <div class="edit-cancel-icon"></div>
                      </button>
                    </div>
                  </div>
                  <div
                    v-if="
                      showCaseTooltip === groupIndex &&
                      !(editingState.groupIndex === groupIndex && editingState.field === 'delo')
                    "
                    class="header-tooltip"
                    :class="{ 'tooltip-bottom': groupIndex === 0 }"
                  >
                    Дело
                  </div>
                </div>
              </div>
            </div>
            <div v-if="editingState.groupIndex !== groupIndex" class="group-actions">
              <!-- Кнопка добавления файлов в группу -->
              <!-- <div
                class="add-files-btn-wrapper"
                @mouseenter="showAddFilesTooltipHandler(groupIndex)"
                @mouseleave="hideAddFilesTooltip()"
              >
                <button
                  class="add-files-btn"
                  :class="{ uploading: groupUploadingStates[groupIndex] }"
                  :disabled="groupUploadingStates[groupIndex]"
                  @click="handleAddFilesToGroup(groupIndex)"
                >
                  <div class="add-files-icon-container">
                    <IconPlus class="add-files-icon" />
                    <div
                      v-if="groupUploadingStates[groupIndex]"
                      class="loading-ring"
                      :style="{ '--progress': groupUploadProgress[groupIndex] + '%' }"
                    ></div>
                  </div>
                </button>
                <div
                  v-if="showAddFilesTooltip === groupIndex"
                  class="add-files-tooltip"
                  :class="{ 'tooltip-bottom': groupIndex === 0 }"
                >
                  Добавить файлы в группу
                </div>
              </div> -->

              <div
                v-if="isGroupReadyForReport(groupIndex)"
                class="download-btn-wrapper"
                @mouseenter="showTooltip(groupIndex)"
                @mouseleave="hideTooltip()"
              >
                <button
                  class="download-btn"
                  @click="openReportConstructor(documentsStore.groupUuids[groupIndex])"
                >
                  <svg
                    class="download-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M7 10L12 15L17 10"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M12 15V3"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </button>
                <div
                  v-if="showDownloadTooltip === groupIndex"
                  class="download-tooltip"
                  :class="{ 'tooltip-bottom': groupIndex === 0 }"
                >
                  Загрузить отчет
                </div>
              </div>
              <div
                class="delete-btn-wrapper"
                @mouseenter="showDeleteTooltipHandler(groupIndex)"
                @mouseleave="hideDeleteTooltip()"
              >
                <button class="delete-btn" @click="showDeleteConfirmationDialog(groupIndex)">
                  <svg
                    class="delete-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      d="M3 6H5H21"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M8 6V4C8 3.46957 8.21071 2.96086 8.58579 2.58579C8.96086 2.21071 9.46957 2 10 2H14C14.5304 2 15.0391 2.21071 15.4142 2.58579C15.7893 2.96086 16 3.46957 16 4V6M19 6V20C19 20.5304 18.7893 21.0391 18.4142 21.4142C18.0391 21.7893 17.5304 22 17 22H7C6.46957 22 5.96086 21.7893 5.58579 21.4142C5.21071 21.0391 5 20.5304 5 20V6H19Z"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M10 11V17"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M14 11V17"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </button>
                <div
                  v-if="showDeleteTooltip === groupIndex"
                  class="delete-tooltip"
                  :class="{ 'tooltip-bottom': groupIndex === 0 }"
                >
                  Удалить группу
                </div>
              </div>
              <div
                class="collapse-btn-wrapper"
                @mouseenter="showCollapseTooltipHandler(groupIndex)"
                @mouseleave="hideCollapseTooltip()"
              >
                <button class="collapse-btn" @click="toggleGroupCollapse(groupIndex)">
                  <div
                    class="collapse-icon"
                    :class="{ collapsed: collapsedGroups[groupIndex] }"
                  ></div>
                </button>
                <div
                  v-if="showCollapseTooltip === groupIndex"
                  class="collapse-tooltip"
                  :class="{ 'tooltip-bottom': groupIndex === 0 }"
                >
                  {{ collapsedGroups[groupIndex] ? 'Открыть' : 'Свернуть' }}
                </div>
              </div>
            </div>
          </div>

          <transition name="collapse">
            <div v-if="!collapsedGroups[groupIndex]" class="files-list">
              <div
                v-for="file in groupDocuments"
                :key="file.file_uuid"
                class="file-item"
                :class="{
                  'file-item-hoverable':
                    file.status === DocumentStatusesEnum.done ||
                    file.status === DocumentStatusesEnum.upgrading,
                  'file-item-selected': fileStore.selectedFileUuid === file.file_uuid,
                }"
                @click="handleFileClick(file)"
              >
                <div class="file-status">
                  <div
                    class="status-indicator"
                    :class="{
                      'status-done': file.status === DocumentStatusesEnum.done,
                      'status-progress': file.status === DocumentStatusesEnum.progress,
                      'status-upgrading': file.status === DocumentStatusesEnum.upgrading,
                    }"
                  >
                    <div
                      v-if="
                        file.status === DocumentStatusesEnum.progress ||
                        file.status === DocumentStatusesEnum.upgrading
                      "
                      class="progress-spinner"
                    ></div>
                  </div>
                </div>
                <div class="file-name">{{ file.filename }}</div>
                <div
                  v-if="file.status === DocumentStatusesEnum.done"
                  class="file-download-btn"
                  @click.stop="openFileReportConstructor(file.file_uuid)"
                  title="Скачать отчет файла"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M7 10L12 15L17 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M12 15V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </div>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>

    <!-- Нижняя часть - drag&drop область -->
    <div
      class="drop-zone"
      :class="{
        'drag-over': isDragOver,
        uploading: documentsStore.isUploading,
      }"
      @dragover="handleDragOver"
      @dragleave="handleDragLeave"
      @drop="handleDrop"
      @click="handleDropZoneClick"
    >
      <div class="drop-content">
        <!-- <div class="drop-icon">
          <div class="drop-icon-shape"></div>
        </div> -->
        <div class="drop-text">
          <p v-if="!documentsStore.isUploading">
            Перетащите изображения сюда или кликните для выбора
          </p>
          <div v-else class="upload-progress">
            <p>Загрузка файлов...</p>
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: documentsStore.uploadProgress + '%' }"
              ></div>
            </div>
            <p class="progress-text">{{ documentsStore.uploadProgress }}%</p>
          </div>
          <p class="drop-hint" v-if="!documentsStore.isUploading">
            * форматы: JPG, JPEG, PNG, BMP, WEBP
          </p>
        </div>
      </div>

      <!-- Скрытый input для выбора файлов -->
      <input
        ref="fileInputRef"
        type="file"
        accept=".jpg,.jpeg,.png,.bmp,.webp,image/jpeg,image/jpg,image/png,image/bmp,image/webp"
        multiple
        style="display: none"
        @change="handleFileInputChange"
      />
    </div>
  </div>

  <!-- Модальное окно подтверждения удаления -->
  <div v-if="showDeleteConfirmation" class="delete-confirmation-overlay" @click="cancelDeleteGroup">
    <div class="delete-confirmation-modal" @click.stop>
      <div class="confirmation-header">
        <h3>Удалить группу?</h3>
      </div>
      <div class="confirmation-content">
        <p>Вы уверены, что хотите удалить эту группу? Это действие нельзя отменить.</p>
      </div>
      <div class="confirmation-actions">
        <button class="cancel-btn" @click="cancelDeleteGroup">Отмена</button>
        <button class="confirm-btn" @click="confirmDeleteGroup">Удалить</button>
      </div>
    </div>
  </div>

  <!-- Конструктор отчетов -->
  <ReportConstructor
    :is-visible="showReportConstructor"
    :group-uuid="selectedGroupUuid"
    @close="closeReportConstructor"
    @generate="handleGenerateReport"
  />
</template>

<style scoped lang="scss">
.menu-wrapper {
  box-shadow: 0 0 10px 0 rgba(0, 0, 0, 0.1);
  border-radius: 10px;
  background-color: #ffffff;
  padding: 20px;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 40px);
  gap: 20px;
}

// Секция документов
.documents-section {
  flex: 1;
  overflow-y: auto;
  overflow-x: visible;
}

.section-title {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 500;
  color: #202124;
  letter-spacing: 0.1px;
  font-weight: bold;
  cursor: default;
}

.groups-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: visible;
}

.group-item {
  border: 2px solid #e8eaed;
  border-radius: 12px;
  background-color: #ffffff;
  transition: all 0.2s ease;
  overflow: visible;

  &:hover {
    border-color: #dadce0;
  }
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background-color: #f8f9fa;
  border-radius: 12px;
  gap: 12px;
}

.group-name-section {
  flex: 0 0 auto;
}

.group-name {
  font-weight: 500;
  color: #202124;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 8px;
  transition: background-color 0.2s ease;
  font-size: 15px;
  display: inline-block;

  &:hover {
    background-color: #e8f0fe;
  }
}

.group-headers {
  display: flex;
  gap: 4px;
  align-items: center;
  background-color: #f0f0f0;
  border-radius: 8px;
  padding: 4px;
  border: 1px solid #e0e0e0;
  transition: all 0.2s ease;
  width: fit-content;

  &:hover {
    border-color: #1a73e8;
  }
}

.group-header-item-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.group-header-item {
  font-weight: 500;
  color: #202124;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 15px;
  display: inline-block;
  white-space: nowrap;
  background-color: transparent;
  position: relative;
  transition: all 0.2s ease;

  &:hover {
    background-color: #e8f0fe;
    color: #1a73e8;
  }
}

.header-tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background-color: #202124;
  color: white;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  z-index: 9999;
  margin-bottom: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  animation: tooltipFadeIn 0.2s ease-out;

  // Стрелочка тултипа
  &::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #202124;
  }

  // Позиционирование снизу для первой группы
  &.tooltip-bottom {
    bottom: auto;
    top: 100%;
    margin-bottom: 0;
    margin-top: 8px;

    &::after {
      top: auto;
      bottom: 100%;
      border-top: none;
      border-bottom: 4px solid #202124;
    }
  }
}

.edit-container {
  display: flex;
  align-items: center;
  gap: 4px;
  background-color: white;
  border: 2px solid #1a73e8;
  border-radius: 6px;
  padding: 4px;
}

.edit-input {
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  font-weight: 500;
  color: #202124;
  padding: 4px 8px;
  min-width: 60px;
  flex: 1;
}

.edit-actions {
  display: flex;
  gap: 2px;
}

.edit-save-btn,
.edit-cancel-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #5f6368;

  &:hover {
    background-color: #e8f0fe;
  }
}

.edit-save-btn {
  border: 1px solid #dadce0;
  border-radius: 4px;

  &:hover {
    border-color: #34a853;
    color: #34a853;
  }
}

.edit-cancel-btn:hover {
  color: #ea4335;
}

.edit-save-icon {
  width: 16px;
  height: 16px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 8px;
    height: 4px;
    border-left: 2px solid currentColor;
    border-bottom: 2px solid currentColor;
    border-radius: 1px;
    transform: translate(-50%, -60%) rotate(-45deg);
  }
}

.edit-cancel-icon {
  width: 16px;
  height: 16px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 12px;
    height: 2px;
    background-color: currentColor;
    border-radius: 1px;
    transform: translate(-50%, -50%) rotate(45deg);
  }

  &::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 12px;
    height: 2px;
    background-color: currentColor;
    border-radius: 1px;
    transform: translate(-50%, -50%) rotate(-45deg);
  }
}

.group-name-input {
  flex: 1;
  border: 2px solid #1a73e8;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 15px;
  outline: none;
  background-color: white;
  color: #202124;
  font-weight: 500;
}

.group-actions {
  display: flex;
  gap: 5px;
  position: relative;
}

.add-files-btn-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.add-files-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #5f6368;
  position: relative;

  &:hover:not(:disabled) {
    background-color: #e8f0fe;
    color: #1a73e8;

    .add-files-icon {
      animation: addFilesBounce 0.6s ease-in-out;
    }
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  &.uploading {
    cursor: not-allowed;
    opacity: 0.8;
  }
}

.add-files-icon-container {
  position: relative;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.add-files-icon {
  width: 20px;
  height: 20px;
  transition: transform 0.2s ease;
  color: currentColor;
  z-index: 2;
}

.loading-ring {
  position: absolute;
  top: 0;
  left: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid #e8eaed;
  border-top: 2px solid #1a73e8;
  animation: spin 1s linear infinite;
  z-index: 1;
}

.add-files-tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background-color: #202124;
  color: white;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  z-index: 9999;
  margin-bottom: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  animation: tooltipFadeIn 0.2s ease-out;

  // Стрелочка тултипа
  &::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #202124;
  }

  // Позиционирование снизу для первой группы
  &.tooltip-bottom {
    bottom: auto;
    top: 100%;
    margin-bottom: 0;
    margin-top: 8px;

    &::after {
      top: auto;
      bottom: 100%;
      border-top: none;
      border-bottom: 4px solid #202124;
    }
  }
}

// Анимация для иконки добавления файлов
@keyframes addFilesBounce {
  0% {
    transform: scale(1);
  }
  25% {
    transform: scale(1.1);
  }
  50% {
    transform: scale(1);
  }
  75% {
    transform: scale(1.05);
  }
  100% {
    transform: scale(1);
  }
}

.download-btn-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.delete-btn-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.collapse-btn-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.download-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #5f6368;

  &:hover {
    background-color: #e8f0fe;
    color: #1a73e8;

    .download-icon {
      animation: downloadBounce 0.6s ease-in-out;
    }
  }
}

.delete-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #5f6368;

  &:hover {
    background-color: #fce8e6;
    color: #ea4335;

    .delete-icon {
      animation: deleteShake 0.6s ease-in-out;
    }
  }
}

.collapse-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #5f6368;

  &:hover {
    background-color: #e8f0fe;
    color: #1a73e8;
  }
}

.download-icon {
  width: 20px;
  height: 20px;
  transition: transform 0.2s ease;
  color: currentColor;
}

.delete-icon {
  width: 20px;
  height: 20px;
  transition: transform 0.2s ease;
  color: currentColor;
}

// Анимация для иконки скачивания
@keyframes downloadBounce {
  0% {
    transform: translateY(0);
  }
  25% {
    transform: translateY(-2px);
  }
  50% {
    transform: translateY(0);
  }
  75% {
    transform: translateY(-1px);
  }
  100% {
    transform: translateY(0);
  }
}

// Анимация для иконки удаления
@keyframes deleteShake {
  0%,
  100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-2px);
  }
  75% {
    transform: translateX(2px);
  }
}

// Стили для тултипа
.download-tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background-color: #202124;
  color: white;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  z-index: 9999;
  margin-bottom: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  animation: tooltipFadeIn 0.2s ease-out;

  // Стрелочка тултипа
  &::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #202124;
  }

  // Позиционирование снизу для первой группы
  &.tooltip-bottom {
    bottom: auto;
    top: 100%;
    margin-bottom: 0;
    margin-top: 8px;

    &::after {
      top: auto;
      bottom: 100%;
      border-top: none;
      border-bottom: 4px solid #202124;
    }
  }
}

// Анимация появления тултипа
@keyframes tooltipFadeIn {
  0% {
    opacity: 0;
    transform: translateX(-50%) translateY(4px);
  }
  100% {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

// Стили для тултипа кнопки сворачивания
.collapse-tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background-color: #202124;
  color: white;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  z-index: 9999;
  margin-bottom: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  animation: tooltipFadeIn 0.2s ease-out;

  // Стрелочка тултипа
  &::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #202124;
  }

  // Позиционирование снизу для первой группы
  &.tooltip-bottom {
    bottom: auto;
    top: 100%;
    margin-bottom: 0;
    margin-top: 8px;

    &::after {
      top: auto;
      bottom: 100%;
      border-top: none;
      border-bottom: 4px solid #202124;
    }
  }
}

// Стили для тултипа удаления
.delete-tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background-color: #202124;
  color: white;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  z-index: 9999;
  margin-bottom: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  animation: tooltipFadeIn 0.2s ease-out;

  // Стрелочка тултипа
  &::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #202124;
  }

  // Позиционирование снизу для первой группы
  &.tooltip-bottom {
    bottom: auto;
    top: 100%;
    margin-bottom: 0;
    margin-top: 8px;

    &::after {
      top: auto;
      bottom: 100%;
      border-top: none;
      border-bottom: 4px solid #202124;
    }
  }
}

.collapse-icon {
  width: 20px;
  height: 20px;
  position: relative;
  transition: transform 0.2s ease;

  &::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 8px;
    height: 8px;
    border-right: 2px solid currentColor;
    border-bottom: 2px solid currentColor;
    border-radius: 1px;
    transform: translate(-50%, -60%) rotate(45deg);
  }

  &.collapsed {
    transform: rotate(180deg);
  }
}

.edit-icon {
  width: 18px;
  height: 18px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 12px;
    height: 12px;
    border: 2px solid currentColor;
    border-radius: 2px;
  }

  &::after {
    content: '';
    position: absolute;
    top: -1px;
    right: -1px;
    width: 4px;
    height: 4px;
    border: 2px solid currentColor;
    border-left: none;
    border-bottom: none;
    border-radius: 0 2px 0 0;
  }
}

.edit-actions {
  display: flex;
  gap: 4px;
}

.save-btn,
.cancel-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 50%;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #5f6368;

  &:hover {
    background-color: #e8f0fe;
  }
}

.save-btn:hover {
  color: #34a853;
}

.cancel-btn:hover {
  color: #ea4335;
}

.save-icon {
  width: 18px;
  height: 18px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 8px;
    height: 4px;
    border-left: 2px solid currentColor;
    border-bottom: 2px solid currentColor;
    border-radius: 1px;
    transform: translate(-50%, -60%) rotate(-45deg);
  }
}

.cancel-icon {
  width: 18px;
  height: 18px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 12px;
    height: 2px;
    background-color: currentColor;
    border-radius: 1px;
    transform: translate(-50%, -50%) rotate(45deg);
  }

  &::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 12px;
    height: 2px;
    background-color: currentColor;
    border-radius: 1px;
    transform: translate(-50%, -50%) rotate(-45deg);
  }
}

.files-list {
  padding: 8px 20px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

// Анимации для сворачивания
.collapse-enter-active,
.collapse-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.collapse-enter-from,
.collapse-leave-to {
  max-height: 0;
  padding: 0 20px;
  opacity: 0;
}

.collapse-enter-to,
.collapse-leave-from {
  max-height: 500px;
  padding: 8px 20px 20px 20px;
  opacity: 1;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  background-color: #f8f9fa;
  border: 2px solid transparent;
  transition: all 0.2s ease;
  cursor: default;

  &.file-item-hoverable {
    cursor: pointer;

    &:hover {
      background-color: #e8f0fe;
    }
  }

  &.file-item-selected {
    background-color: #e8f0fe;
    border: 2px solid #1a73e8;
    box-shadow: 0 2px 8px rgba(26, 115, 232, 0.15);
  }
}

.file-status {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
}

.status-indicator {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background-color: #dadce0;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;

  &.status-done {
    background-color: #34a853;
  }

  &.status-progress {
    background-color: #fb9004;
    animation: pulse 1.5s ease-in-out infinite;
  }

  &.status-upgrading {
    background-color: #fbbc04;
    animation: pulse 1.5s ease-in-out infinite;
  }
}

.progress-spinner {
  width: 9px;
  height: 9px;
  border: 1px solid #ffffff;
  border-top: 1px solid transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.1);
    opacity: 0.8;
  }
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.file-name {
  flex: 1;
  font-size: 14px;
  color: #3c4043;
  font-weight: 400;
}

.file-download-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: none;
  border: none;
  cursor: pointer;
  color: #5f6368;
  transition: all 0.2s ease;
  opacity: 0;
  transform: scale(0.8);
}

.file-item:hover .file-download-btn {
  opacity: 1;
  transform: scale(1);
}

.file-download-btn:hover {
  background-color: #e8f0fe;
  color: #1a73e8;
  transform: scale(1.1);
}

.file-download-btn svg {
  width: 16px;
  height: 16px;
}

// Drag & Drop область
.drop-zone {
  border: 2px dashed #dadce0;
  border-radius: 12px;
  padding: 32px 24px;
  text-align: center;
  background-color: #f8f9fa;
  transition: all 0.3s ease;
  cursor: pointer;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover {
    border-color: #1a73e8;
    background-color: #e8f0fe;
  }

  &.drag-over {
    border-color: #1a73e8;
    background-color: #e8f0fe;
    transform: scale(1.01);
    box-shadow: 0 4px 12px rgba(26, 115, 232, 0.15);
  }

  &.uploading {
    border-color: #fbbc04;
    background-color: #fef7e0;
    cursor: not-allowed;

    .drop-text p {
      color: #f9ab00;
      font-weight: 600;
    }
  }
}

.drop-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  // gap: 10px;
}

.drop-icon {
  width: 144px;
  height: 144px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.7;
  margin-bottom: -20px;
  margin-top: -20px;
}

.drop-icon-shape {
  width: 120px;
  height: 120px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: 12px;
    left: 50%;
    transform: translateX(-50%);
    width: 24px;
    height: 30px;
    background-color: #5f6368;
  }

  &::after {
    content: '';
    position: absolute;
    top: 42px;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 36px solid transparent;
    border-right: 36px solid transparent;
    border-top: 48px solid #5f6368;
  }
}

.drop-text {
  color: #5f6368;

  p {
    margin: 0;
    font-size: 15px;
    font-weight: 500;
  }

  .drop-hint {
    font-size: 13px;
    color: #9aa0a6;
    font-weight: 400;
  }
}

// Стили для статистики
.stats-section {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border-radius: 12px;
  border: 1px solid #e0e0e0;
}

.stats-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  padding: 8px 12px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
  cursor: default;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  }
}

.stats-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  flex-shrink: 0;

  svg {
    width: 18px;
    height: 18px;
  }

  &.total {
    background: #e3f2fd;
    color: #1976d2;
  }

  &.processing {
    background: #fff3e0;
    color: #f57c00;
  }

  &.completed {
    background: #e8f5e8;
    color: #388e3c;
  }
}

.stats-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.stats-number {
  font-size: 16px;
  font-weight: 600;
  color: #202124;
  line-height: 1.2;
}

.stats-label {
  font-size: 11px;
  color: #5f6368;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  line-height: 1.2;
  white-space: nowrap;
}

// Адаптивность
@media (max-width: 768px) {
  .menu-wrapper {
    padding: 15px;
  }

  .stats-section {
    flex-direction: column;
    gap: 8px;
    padding: 12px;
  }

  .stats-item {
    padding: 6px 10px;
  }

  .stats-number {
    font-size: 14px;
  }

  .stats-label {
    font-size: 10px;
  }

  .group-header {
    padding: 10px 12px;
  }

  .files-list {
    padding: 8px 12px;
  }

  .drop-zone {
    padding: 20px 15px;
    min-height: 100px;
  }
}

// Стили для индикатора прогресса загрузки
.upload-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.progress-bar {
  width: 200px;
  height: 8px;
  background-color: #e8f0fe;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1a73e8, #34a853);
  border-radius: 4px;
  transition: width 0.3s ease;
  position: relative;

  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
    animation: shimmer 1.5s infinite;
  }
}

.progress-text {
  font-size: 14px;
  font-weight: 600;
  color: #1a73e8;
  margin: 0;
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

// Стили для модального окна подтверждения удаления
.delete-confirmation-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  animation: fadeIn 0.2s ease-out;
}

.delete-confirmation-modal {
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
  max-width: 400px;
  width: 90%;
  animation: slideIn 0.3s ease-out;
}

.confirmation-header {
  padding: 24px 24px 0 24px;

  h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: #202124;
  }
}

.confirmation-content {
  padding: 16px 24px;

  p {
    margin: 0;
    font-size: 14px;
    color: #5f6368;
    line-height: 1.5;
  }
}

.confirmation-actions {
  padding: 0 24px 24px 24px;
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.cancel-btn,
.confirm-btn {
  padding: 10px 20px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
}

.cancel-btn {
  background-color: #f8f9fa;
  color: #5f6368;
  border: 1px solid #dadce0;

  &:hover {
    background-color: #e8f0fe;
    color: #1a73e8;
  }
}

.confirm-btn {
  background-color: #ea4335;
  color: white;

  &:hover {
    background-color: #d33b2c;
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
</style>
