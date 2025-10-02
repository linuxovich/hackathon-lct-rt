import { ref } from 'vue';
import { defineStore } from 'pinia';
import { API_ROUTES, client, uploadClient } from '@/constants';
import type { Document, FileContent } from '@/interfaces/documents';

export const useDocumentsStore = defineStore('documents', () => {
  // Store version: 1.2 - with group_uuid support
  const all = ref<Array<Array<Document>>>([]);
  const isUploading = ref(false);
  const uploadProgress = ref(0);
  const groupUuids = ref<string[]>([]);

  // Функции для работы с localStorage
  function saveGroupUuids() {
    localStorage.setItem('group_uuids', JSON.stringify(groupUuids.value));
  }

  function loadGroupUuids() {
    const stored = localStorage.getItem('group_uuids');
    if (stored) {
      groupUuids.value = JSON.parse(stored);
    }
  }

  function addGroupUuid(uuid: string) {
    if (!groupUuids.value.includes(uuid)) {
      groupUuids.value.push(uuid);
      saveGroupUuids();
    }
  }

  function removeGroup(groupIndex: number) {
    if (groupIndex >= 0 && groupIndex < groupUuids.value.length) {
      // Удаляем группу из массива
      groupUuids.value.splice(groupIndex, 1);
      all.value.splice(groupIndex, 1);

      // Сохраняем изменения в localStorage
      saveGroupUuids();
    }
  }

  async function fetchAllDocuments() {
    // Загружаем group_uuids из localStorage
    loadGroupUuids();

    if (groupUuids.value.length === 0) {
      all.value = [];
      return;
    }

    // Загружаем документы для каждой группы
    const documentsPromises = groupUuids.value.map(async (groupUuid) => {
      try {
        const { data } = await client.get<Array<Document>>(API_ROUTES.documents.all(groupUuid));
        return data;
      } catch (error) {
        console.error(`Ошибка загрузки документов для группы ${groupUuid}:`, error);
        return [];
      }
    });

    const documentsArrays = await Promise.all(documentsPromises);
    all.value = documentsArrays;
  }

  async function uploadFiles(files: File[], fond?: string, opis?: string, delo?: string) {
    console.log('=== STORE: uploadFiles вызван ===');
    console.log(
      'Файлы:',
      files.map((f) => ({ name: f.name, size: f.size, type: f.type })),
    );
    console.log('Параметры:', { fond, opis, delo });

    isUploading.value = true;
    try {
      const formData = new FormData();

      // Добавляем все файлы
      files.forEach((file) => {
        formData.append('files', file);
      });

      // Добавляем поля - если не переданы, то отправляем пустую строку
      formData.append('fond', fond || '');
      formData.append('opis', opis || '');
      formData.append('delo', delo || '');

      console.log('Отправляем запрос на:', API_ROUTES.upload.files());
      console.log('Form data содержимое:');
      for (const [key, value] of formData.entries()) {
        console.log(`${key}:`, value);
      }

      const response = await uploadClient.post<{
        fond: string;
        opis: string;
        delo: string;
        group_uuid: string;
      }>(API_ROUTES.upload.files(), formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        // Добавляем обработчик прогресса загрузки
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            uploadProgress.value = percentCompleted;
            console.log(`Прогресс загрузки: ${percentCompleted}%`);
          }
        },
      });

      console.log('Ответ сервера:', response.data);
      console.log('Статус:', response.status);

      // Сохраняем group_uuid из ответа
      const { group_uuid } = response.data;
      console.log('Получен group_uuid:', group_uuid);
      addGroupUuid(group_uuid);

      // Обновляем список документов после успешной загрузки
      console.log('Обновляем список документов...');
      await fetchAllDocuments();
      console.log('=== STORE: uploadFiles завершен успешно ===');
    } catch (error) {
      console.error('=== STORE: Ошибка загрузки файлов ===');
      console.error('Ошибка:', error);
      if (error && typeof error === 'object' && 'response' in error) {
        const axiosError = error as {
          response: { data: unknown; status: number; headers: Record<string, string> };
        };
        console.error('Ответ сервера:', axiosError.response.data);
        console.error('Статус:', axiosError.response.status);
        console.error('Заголовки:', axiosError.response.headers);
      }
      throw error;
    } finally {
      isUploading.value = false;
      uploadProgress.value = 0;
    }
  }

  // Новая функция для загрузки файлов в существующую группу
  async function uploadFilesToGroup(files: File[], groupUuid: string) {
    console.log('=== STORE: uploadFilesToGroup вызван ===');
    console.log(
      'Файлы:',
      files.map((f) => ({ name: f.name, size: f.size, type: f.type })),
    );
    console.log('Group UUID:', groupUuid);

    isUploading.value = true;
    try {
      const formData = new FormData();

      // Добавляем все файлы
      files.forEach((file) => {
        formData.append('files', file);
      });

      console.log('Отправляем запрос на:', API_ROUTES.upload.filesToGroup(groupUuid));
      console.log('Form data содержимое:');
      for (const [key, value] of formData.entries()) {
        console.log(`${key}:`, value);
      }

      const response = await uploadClient.post(
        API_ROUTES.upload.filesToGroup(groupUuid),
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          // Добавляем обработчик прогресса загрузки
          onUploadProgress: (progressEvent) => {
            if (progressEvent.total) {
              const percentCompleted = Math.round(
                (progressEvent.loaded * 100) / progressEvent.total,
              );
              uploadProgress.value = percentCompleted;
              console.log(`Прогресс загрузки: ${percentCompleted}%`);
            }
          },
        },
      );

      console.log('Ответ сервера:', response.data);
      console.log('Статус:', response.status);

      // Обновляем список документов после успешной загрузки
      console.log('Обновляем список документов...');
      await fetchAllDocuments();
      console.log('=== STORE: uploadFilesToGroup завершен успешно ===');
    } catch (error) {
      console.error('=== STORE: Ошибка загрузки файлов в группу ===');
      console.error('Ошибка:', error);
      if (error && typeof error === 'object' && 'response' in error) {
        const axiosError = error as {
          response: { data: unknown; status: number; headers: Record<string, string> };
        };
        console.error('Ответ сервера:', axiosError.response.data);
        console.error('Статус:', axiosError.response.status);
        console.error('Заголовки:', axiosError.response.headers);
      }
      throw error;
    } finally {
      isUploading.value = false;
      uploadProgress.value = 0;
    }
  }

  return {
    all,
    isUploading,
    uploadProgress,
    groupUuids,
    fetchAllDocuments,
    uploadFiles,
    uploadFilesToGroup,
    addGroupUuid,
    loadGroupUuids,
    removeGroup,
  };
});

export const useFileStore = defineStore('file', () => {
  const content = ref<FileContent>();
  const selectedFileUuid = ref<string | null>(null);

  async function fetchFileContent(file_uuid: string, stage: string = 'done') {
    const { data } = await client.get<FileContent>(API_ROUTES.files.content(file_uuid, stage));
    content.value = data;
  }

  function setSelectedFile(file_uuid: string) {
    selectedFileUuid.value = file_uuid;
  }

  function clearSelectedFile() {
    selectedFileUuid.value = null;
    content.value = undefined;
  }

  async function updateFileContent(file_uuid: string, updatedContent: FileContent) {
    console.log('Store: updateFileContent вызвана, file_uuid:', file_uuid);
    console.log('Store: отправляем PUT запрос на:', API_ROUTES.files.updateContent(file_uuid));
    console.log('Store: данные для отправки:', updatedContent);

    const { data } = await client.put(API_ROUTES.files.updateContent(file_uuid), updatedContent, {
      params: { stage: 'done' },
    });
    console.log('Store: ответ от сервера:', data);
    // Обновляем локальное состояние после успешного обновления
    content.value = data;
    return data;
  }

  return {
    content,
    selectedFileUuid,
    fetchFileContent,
    setSelectedFile,
    clearSelectedFile,
    updateFileContent,
  };
});
