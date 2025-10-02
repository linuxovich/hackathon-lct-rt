import axios from 'axios';

// const API_BASE = 'http://127.0.0.1:9425';
const API_BASE = 'http://89.169.182.117:8000';

export const API_ROUTES = {
  // user: {
  //   profile: `/user/profile`,
  //   freelancer: {
  //     statistics: `/user/freelancer/statistics`,
  //     permissions: `/user/freelancer/permissions`,
  //   },
  // },
  // tasks: {
  //   all: (limit: number, offset: number) => `/tasks?limit=${limit}&offset=${offset}`,
  //   selected: (id: string) => `/tasks/${id}`,
  // },
  // showcases: {
  //   all: (limit: number, offset: number) => `/showcases?limit=${limit}&offset=${offset}`,
  // },
  documents: {
    all: (group_uuid: string) => `/api/v1/groups/${group_uuid}/files`,
  },
  groups: {
    report: (group_uuid: string) => `/api/v1/groups/${group_uuid}/report?format=xlsx&stage=done`,
  },
  upload: {
    files: () => `/api/v1/groups/upload-files`,
    filesToGroup: (group_uuid: string) => `/api/v1/groups/${group_uuid}/upload-files`,
  },
  files: {
    content: (file_uuid: string, stage: string = 'done') =>
      `/api/v1/files/${file_uuid}/content?stage=${stage}`,
    image: (file_uuid: string) => `/api/v1/files/${file_uuid}/image`,
    updateContent: (file_uuid: string) => `/api/v1/files/${file_uuid}/content`,
  },
};

export const client = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

// Отдельный клиент для загрузки файлов с увеличенным таймаутом
export const uploadClient = axios.create({
  baseURL: API_BASE,
  timeout: 300000, // 5 минут для загрузки файлов
});
