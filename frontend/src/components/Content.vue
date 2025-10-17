<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import TextItem from './TextItem.vue';
import { useFileStore, useDocumentsStore } from '@/stores/documents';
import { API_ROUTES, client } from '@/constants';
import { DocumentStatusesEnum } from '@/interfaces/documents';

const fileStore = useFileStore();
const documentsStore = useDocumentsStore();

// Computed свойство для URL изображения
const imageUrl = computed(() => {
  if (fileStore.content?.file_uuid) {
    return `${client.defaults.baseURL}${API_ROUTES.files.image(fileStore.content.file_uuid)}`;
  }
  return null; // Нет fallback изображения
});

// Состояние загрузки изображения
const isImageLoading = ref(false);
const imageLoadError = ref(false);

const hoveredIndex = ref<number | null>(null);
// Добавляем переменную для отслеживания наведения на изображение
const imageHoveredIndex = ref<number | null>(null);

// Computed свойство для объединения наведения на текст и изображение
const effectiveHoveredIndex = computed(() => {
  // Приоритет у наведения на текст (если пользователь наводит на текст)
  if (hoveredIndex.value !== null) {
    return hoveredIndex.value;
  }
  // Иначе используем наведение на изображение
  return imageHoveredIndex.value;
});

// Computed свойство для определения, заблокированы ли элементы
const isInteractionBlocked = computed(() => {
  return editingIndex.value !== null;
});

// Функция для плавной прокрутки к элементу
const scrollToElement = (index: number) => {
  const textSection = document.querySelector('.text-section');
  if (!textSection) return;

  const textItems = textSection.querySelectorAll('.text-item');
  const targetElement = textItems[index] as HTMLElement;

  if (targetElement) {
    // Проверяем, виден ли элемент
    const rect = targetElement.getBoundingClientRect();
    const containerRect = textSection.getBoundingClientRect();

    // Если элемент не полностью виден, прокручиваем
    const isFullyVisible = rect.top >= containerRect.top && rect.bottom <= containerRect.bottom;

    if (!isFullyVisible) {
      targetElement.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
        inline: 'nearest'
      });
    }
  }
};

// Переменная для debounce
let scrollTimeout: number | null = null;

// Watcher для автоматической прокрутки при наведении на изображение
watch(imageHoveredIndex, (newIndex) => {
  if (newIndex !== null) {
    // Очищаем предыдущий timeout
    if (scrollTimeout) {
      clearTimeout(scrollTimeout);
    }

    // Небольшая задержка для плавности и debounce
    scrollTimeout = setTimeout(() => {
      scrollToElement(newIndex);
    }, 150);
  }
});
const editingIndex = ref<number | null>(null);
const isSaving = ref(false);
const imageWrapperWidth = ref(0);
const imageWrapperHeight = ref(0);
const imageNaturalWidth = ref(0);
const imageNaturalHeight = ref(0);
const imageDisplayWidth = ref(0);
const imageDisplayHeight = ref(0);
const imageAspectRatio = ref(1);
const imageOffsetX = ref(0);
const imageOffsetY = ref(0);
// Удаляем переменные для лупы
// const isMagnifierVisible = ref(false);
// const magnifierX = ref(0);
// const magnifierY = ref(0);
// const magnifierRelativeX = ref(0);
// const magnifierRelativeY = ref(0);
// const magnifierSize = 259; // размер увеличителя
// const magnifierScale = 2; // коэффициент увеличения

// Добавляем переменные для подсветки баундинг боксов
const hoveredBoundingBox = ref<number | null>(null);
const hoveredLineIndex = ref<number | null>(null);

// Преобразуем координаты один раз при загрузке
const processedContent = ref<
  Array<{
    id: string;
    coords: Array<{ x: number; y: number }>;
    text: string;
    regionIndex?: number;
  }>
>([]);

// Координаты regions для отображения bounding_box
const regionsContent = ref<
  Array<{
    coords: Array<{ x: number; y: number }>;
    text: string;
  }>
>([]);

// Computed свойство для получения статуса выбранного документа
const selectedDocumentStatus = computed(() => {
  if (!fileStore.selectedFileUuid || !documentsStore.all) return null;

  // Ищем документ с выбранным file_uuid во всех группах
  for (const groupDocuments of documentsStore.all) {
    const document = groupDocuments.find((doc) => doc.file_uuid === fileStore.selectedFileUuid);
    if (document) {
      return document.status;
    }
  }
  return null;
});

// Computed свойство для получения всех именованных сущностей
const namedEntities = computed(() => {
  if (!fileStore.content?.json?.regions) return [];

  const allEntities: Array<{
    entity_type: string;
    entity_value: string;
    details: string;
    region_id: string;
  }> = [];

  fileStore.content.json.regions.forEach((region) => {
    if (region.named_entities && region.named_entities.length > 0) {
      region.named_entities.forEach((entity) => {
        allEntities.push({
          ...entity,
          region_id: region.id,
        });
      });
    }
  });

  return allEntities;
});

// Функция для парсинга строки координат
function parseCoordinates(coordString: string): Array<{ x: number; y: number }> {
  if (!coordString) return [];

  return coordString.split(' ').map((pair) => {
    const [x, y] = pair.split(',').map(Number);
    return { x, y };
  });
}

// Функция для получения читаемого названия типа сущности
function getEntityTypeLabel(entityType: string): string {
  const typeLabels: Record<string, string> = {
    person: 'Персона',
    place: 'Место',
    document: 'Документ',
    date: 'Дата',
    organization: 'Организация',
    event: 'Событие',
    other: 'Прочее',
  };

  return typeLabels[entityType] || entityType;
}

// ResizeObserver для отслеживания изменений размера
let resizeObserver: ResizeObserver | null = null;

// Watch для обновления координат при изменении content
watch(
  () => fileStore.content,
  (newContent) => {
    if (newContent?.json?.scan?.dimensions && newContent?.json?.regions) {
      const { width, height } = newContent.json.scan.dimensions;

      // Собираем все lines из всех regions
      const allLines: Array<{
        id: string;
        coords: Array<{ x: number; y: number }>;
        text: string;
        regionIndex: number;
      }> = [];
      const allRegions: Array<{ coords: Array<{ x: number; y: number }>; text: string }> = [];

      newContent.json.regions.forEach((region, regionIndex) => {
        // Обрабатываем lines
        if (region.lines) {
          region.lines.forEach((line) => {
            // Фильтруем пустые строки и строки с дефисом - пропускаем строки с пустым, только пробельными символами или дефисом
            const text = line.text || '';
            if (text.trim() === '' || text.trim() === '-') {
              return; // Пропускаем пустые строки и строки с дефисом
            }

            const originalCoords = line.coordinates?.original;
            if (originalCoords) {
              const parsedCoords = parseCoordinates(originalCoords);
              allLines.push({
                id: line.id,
                coords: parsedCoords.map((coord) => ({
                  x: (coord.x / width) * 100,
                  y: (coord.y / height) * 100,
                })),
                text: text,
                regionIndex: regionIndex,
              });
            } else {
              // Если нет координат, добавляем без них
              allLines.push({
                id: line.id,
                coords: [],
                text: text,
                regionIndex: regionIndex,
              });
            }
          });
        }

        // Обрабатываем regions bounding_box
        const boundingBox = region.coordinates?.bounding_box;
        if (boundingBox) {
          const regionCoords = [
            { x: boundingBox.top_left.x, y: boundingBox.top_left.y },
            { x: boundingBox.top_right.x, y: boundingBox.top_right.y },
            { x: boundingBox.bottom_right.x, y: boundingBox.bottom_right.y },
            { x: boundingBox.bottom_left.x, y: boundingBox.bottom_left.y },
          ];

          allRegions.push({
            coords: regionCoords.map((coord) => ({
              x: (coord.x / width) * 100,
              y: (coord.y / height) * 100,
            })),
            text: region.concatenated_text || '',
          });
        }
      });

      processedContent.value = allLines.reverse();
      regionsContent.value = allRegions;

      // Когда контент загружен, сбрасываем состояние загрузки
      isImageLoading.value = false;
      imageLoadError.value = false;
    }
  },
  { immediate: true },
);

// Watch для загрузки данных при изменении выбранного файла
watch(
  () => fileStore.selectedFileUuid,
  (newFileUuid) => {
    // Закрываем редактирование при смене файла
    editingIndex.value = null;
    hoveredIndex.value = null;

    if (newFileUuid) {
      isImageLoading.value = true;
      imageLoadError.value = false;
      // Контент будет загружен из LeftMenu.vue с правильным статусом
    } else {
      // Сбрасываем состояние при отмене выбора файла
      isImageLoading.value = false;
      imageLoadError.value = false;
    }
  },
);

// Обработчики для изображения
const handleImageLoad = (event: Event) => {
  isImageLoading.value = false;
  imageLoadError.value = false;

  const img = event.target as HTMLImageElement;
  imageNaturalWidth.value = img.naturalWidth;
  imageNaturalHeight.value = img.naturalHeight;
  imageAspectRatio.value = img.naturalWidth / img.naturalHeight;

  updateImageWrapperSize();
};

const handleImageError = () => {
  isImageLoading.value = false;
  imageLoadError.value = true;
};

const highlightedCoords = computed(() => {
  // Если есть активное редактирование, показываем выделение для редактируемого элемента
  if (editingIndex.value !== null) {
    return processedContent.value[editingIndex.value]?.coords || [];
  }
  // Иначе показываем выделение при наведении на текст или изображение
  if (effectiveHoveredIndex.value !== null) {
    return processedContent.value[effectiveHoveredIndex.value]?.coords || [];
  }
  return [];
});

// Определяем, какой region показать при hover или редактировании
const highlightedRegionIndex = computed(() => {
  // Приоритет у редактирования
  if (editingIndex.value !== null) {
    return processedContent.value[editingIndex.value]?.regionIndex;
  }
  // Иначе показываем при наведении на текст или изображение
  if (effectiveHoveredIndex.value !== null) {
    return processedContent.value[effectiveHoveredIndex.value]?.regionIndex;
  }
  // Или при наведении на изображение (синие баундинг боксы) - только если нет красного
  if (hoveredBoundingBox.value !== null && hoveredLineIndex.value === null) {
    return hoveredBoundingBox.value;
  }
  return null;
});

// Функция для обновления текста элемента
const updateItemText = async (index: number, newText: string) => {
  if (processedContent.value[index] && fileStore.content) {
    const item = processedContent.value[index];

    // Обновляем текст в processedContent
    item.text = newText;

    // Находим и обновляем соответствующий line в JSON
    const regionIndex = item.regionIndex;
    if (regionIndex !== undefined && fileStore.content.json.regions[regionIndex]) {
      const region = fileStore.content.json.regions[regionIndex];
      const lineIndex = region.lines.findIndex((line) => line.id === item.id);

      if (lineIndex !== -1) {
        // Обновляем текст в JSON
        region.lines[lineIndex].text = newText;

        // Отправляем PUT запрос для сохранения изменений
        await saveContentToServer();
      }
    }
  }
};

// Функция для начала редактирования
const startEditing = (index: number) => {
  editingIndex.value = index;
  hoveredIndex.value = null; // Сбрасываем hover при начале редактирования
  imageHoveredIndex.value = null; // Сбрасываем наведение на изображение
};

// Функция для завершения редактирования
const finishEditing = () => {
  editingIndex.value = null;
};

// Функция для обработки клика по красному баундинг боксу
const handleBoundingBoxClick = () => {
  // Если уже редактируется, блокируем клики
  if (editingIndex.value !== null) {
    return;
  }

  // Определяем индекс элемента, который соответствует текущему highlightedCoords
  if (effectiveHoveredIndex.value !== null) {
    startEditing(effectiveHoveredIndex.value);
  } else {
    // Если нет активного hover, но есть highlightedCoords,
    // значит пользователь кликнул по баундинг боксу напрямую
    // В этом случае нужно найти соответствующий элемент по координатам
    if (highlightedCoords.value.length > 0) {
      // Ищем элемент, который соответствует текущим highlightedCoords
      for (let i = 0; i < processedContent.value.length; i++) {
        const item = processedContent.value[i];
        if (item.coords.length > 0 &&
            JSON.stringify(item.coords) === JSON.stringify(highlightedCoords.value)) {
          startEditing(i);
          return;
        }
      }
    }
  }
};

// Функция для отправки обновленного контента на сервер
const saveContentToServer = async () => {
  if (!fileStore.content || !fileStore.selectedFileUuid) {
    console.error('Нет данных для сохранения');
    return;
  }

  if (isSaving.value) {
    return;
  }

  isSaving.value = true;

  try {
    const file_uuid = fileStore.selectedFileUuid;
    const stage = 'done';

    await client.put(
      `/api/v1/files/${file_uuid}/content?stage=${stage}`,
      fileStore.content,
    );
  } catch (error) {
    console.error('Ошибка при сохранении изменений:', error);
    // Можно добавить уведомление пользователю об ошибке
    alert('Ошибка при сохранении изменений. Попробуйте еще раз.');
  } finally {
    isSaving.value = false;
  }
};

// Вспомогательная функция для поиска элемента по оригинальному ID
// const findItemById = (id: string) => {
//   return processedContent.value.find(item => item.id === id);
// };

// Функция для проверки, находится ли точка внутри полигона
const isPointInPolygon = (point: { x: number; y: number }, polygon: Array<{ x: number; y: number }>): boolean => {
  if (polygon.length < 3) return false;

  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].x;
    const yi = polygon[i].y;
    const xj = polygon[j].x;
    const yj = polygon[j].y;

    if (((yi > point.y) !== (yj > point.y)) &&
        (point.x < (xj - xi) * (point.y - yi) / (yj - yi) + xi)) {
      inside = !inside;
    }
  }
  return inside;
};

// Функции для обработки наведения на изображение
const handleImageMouseMove = (event: MouseEvent) => {
  // Если идет редактирование, блокируем обработку наведения
  if (editingIndex.value !== null) {
    return;
  }

  const imageContainer = event.currentTarget as HTMLElement;
  const rect = imageContainer.getBoundingClientRect();

  // Рассчитываем позицию относительно изображения
  const relativeX = event.clientX - rect.left - imageOffsetX.value;
  const relativeY = event.clientY - rect.top - imageOffsetY.value;

  // Проверяем, что мышь находится над изображением
  if (
    relativeX >= 0 &&
    relativeX <= imageDisplayWidth.value &&
    relativeY >= 0 &&
    relativeY <= imageDisplayHeight.value
  ) {
    // Конвертируем координаты в проценты
    const pointX = (relativeX / imageDisplayWidth.value) * 100;
    const pointY = (relativeY / imageDisplayHeight.value) * 100;

    const mousePoint = { x: pointX, y: pointY };

    // Сбрасываем предыдущие значения
    hoveredBoundingBox.value = null;
    hoveredLineIndex.value = null;
    imageHoveredIndex.value = null;

    // Сначала проверяем lines (красные баундинг боксы) - они имеют приоритет
    for (let i = 0; i < processedContent.value.length; i++) {
      const line = processedContent.value[i];
      if (line.coords.length > 2) {
        const isInside = isPointInPolygon(mousePoint, line.coords);
        if (isInside) {
          hoveredLineIndex.value = i;
          imageHoveredIndex.value = i; // Устанавливаем индекс для подсветки текста
          hoveredBoundingBox.value = null; // Сбрасываем синий, если нашли красный
          break;
        }
      }
    }

    // Если не нашли в lines, проверяем regions (синие баундинг боксы)
    if (hoveredLineIndex.value === null) {
      for (let i = 0; i < regionsContent.value.length; i++) {
        const region = regionsContent.value[i];
        if (region.coords.length > 2) {
          const isInside = isPointInPolygon(mousePoint, region.coords);
          if (isInside) {
            hoveredBoundingBox.value = i;
            break;
          }
        }
      }
    }
  } else {
    hoveredBoundingBox.value = null;
    hoveredLineIndex.value = null;
  }
};

const handleImageMouseLeave = () => {
  hoveredBoundingBox.value = null;
  hoveredLineIndex.value = null;
  imageHoveredIndex.value = null;
};

// Функция для обновления размеров контейнера
const updateImageWrapperSize = () => {
  const imageWrapper = document.querySelector('.image-wrapper') as HTMLElement;
  if (imageWrapper && imageNaturalWidth.value > 0 && imageNaturalHeight.value > 0) {
    const containerWidth = imageWrapper.offsetWidth;
    const containerHeight = imageWrapper.offsetHeight;

    // Рассчитываем размеры изображения с учетом object-fit: contain
    const containerAspectRatio = containerWidth / containerHeight;

    if (imageAspectRatio.value > containerAspectRatio) {
      // Изображение шире контейнера - ограничиваем по ширине
      imageDisplayWidth.value = containerWidth;
      imageDisplayHeight.value = containerWidth / imageAspectRatio.value;
    } else {
      // Изображение выше контейнера - ограничиваем по высоте
      imageDisplayHeight.value = containerHeight;
      imageDisplayWidth.value = containerHeight * imageAspectRatio.value;
    }

    // Рассчитываем смещение для центрирования изображения
    imageOffsetX.value = (containerWidth - imageDisplayWidth.value) / 2;
    imageOffsetY.value = (containerHeight - imageDisplayHeight.value) / 2;

    imageWrapperWidth.value = imageDisplayWidth.value;
    imageWrapperHeight.value = imageDisplayHeight.value;
  }
};

onMounted(() => {
  // Контент будет загружен из LeftMenu.vue с правильным статусом
  // при клике на файл

  // Ждем загрузки изображения и обновляем размеры
  const img = document.querySelector('.metric-book-image') as HTMLImageElement;
  if (img) {
    if (img.complete) {
      // Изображение уже загружено
      updateImageWrapperSize();
    } else {
      // Ждем загрузки изображения
      img.onload = () => {
        updateImageWrapperSize();
      };
    }
  }

  // Настраиваем ResizeObserver для отслеживания изменений размера контейнера
  const imageWrapper = document.querySelector('.image-wrapper') as HTMLElement;
  if (imageWrapper && window.ResizeObserver) {
    resizeObserver = new ResizeObserver(() => {
      updateImageWrapperSize();
    });
    resizeObserver.observe(imageWrapper);
  }

  window.addEventListener('resize', updateImageWrapperSize);
});

onUnmounted(() => {
  window.removeEventListener('resize', updateImageWrapperSize);
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  // Очищаем timeout при размонтировании
  if (scrollTimeout) {
    clearTimeout(scrollTimeout);
    scrollTimeout = null;
  }
});
</script>

<template>
  <div class="content">
    <!-- Заглушка, когда не выбран файл -->
    <div v-if="!fileStore.selectedFileUuid" class="placeholder">
      <div class="placeholder-content">
        <!-- <div class="placeholder-icon">
          <div class="placeholder-icon-shape"></div>
        </div> -->
        <h3 class="placeholder-title">Загрузите изображения для начала работы</h3>
        <p class="placeholder-description">
          Перетащите изображения в область загрузки слева и дождитесь обработки файлов.
        </p>
        <div class="placeholder-steps">
          <div class="step">
            <div class="step-number">1</div>
            <div class="step-text">Загрузите изображения</div>
          </div>
          <div class="step">
            <div class="step-number">2</div>
            <div class="step-text">Дождитесь обработки</div>
          </div>
          <div class="step">
            <div class="step-number">3</div>
            <div class="step-text">Выберите файл для просмотра</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Основной контент, когда выбран файл -->
    <div v-else class="content-container">
      <!-- Левая часть - картинка -->
      <div class="image-section">
        <div class="image-wrapper">
          <!-- Индикатор загрузки -->
          <div v-if="isImageLoading" class="image-loading">
            <div class="loading-spinner"></div>
            <p class="loading-text">Загрузка изображения...</p>
          </div>

          <!-- Ошибка загрузки -->
          <div v-else-if="imageLoadError" class="image-error">
            <div class="error-icon">⚠️</div>
            <p class="error-text">Ошибка загрузки изображения</p>
          </div>

          <!-- Адаптивный контейнер изображения -->
          <div
            v-else-if="imageUrl"
            class="image-container"
            @mousemove="handleImageMouseMove"
            @mouseleave="handleImageMouseLeave"
          >
            <img
              :src="imageUrl"
              alt="Content image"
              class="metric-book-image"
              @load="handleImageLoad"
              @error="handleImageError"
            />

            <svg
              v-if="
                highlightedCoords.length > 1 ||
                (highlightedRegionIndex !== null &&
                  highlightedRegionIndex !== undefined &&
                  highlightedRegionIndex < regionsContent.length)
              "
              class="connection-lines"
              :width="imageDisplayWidth"
              :height="imageDisplayHeight"
              :style="`transform: translate(${imageOffsetX}px, ${imageOffsetY}px);`"
            >
              <!-- Regions bounding boxes (синие рамки) - показываем при hover на соответствующий текст или при наведении на изображение -->
              <g
                v-if="
                  highlightedRegionIndex !== null &&
                  highlightedRegionIndex !== undefined &&
                  highlightedRegionIndex < regionsContent.length
                "
                style="pointer-events: none;"
              >
                <polygon
                  v-if="regionsContent[highlightedRegionIndex]?.coords.length > 2"
                  :points="
                    regionsContent[highlightedRegionIndex].coords
                      .map(
                        (coord: { x: number; y: number }) =>
                          `${(coord.x / 100) * imageDisplayWidth},${(coord.y / 100) * imageDisplayHeight}`,
                      )
                      .join(' ')
                  "
                  fill="rgba(68, 68, 255, 0.1)"
                  stroke="#4444ff"
                  stroke-width="3"
                />
              </g>

              <!-- Lines coordinates (красные рамки) -->
              <g v-if="highlightedCoords.length > 1">
                <!-- Полупрозрачная заливка внутри контура -->
                <polygon
                  v-if="highlightedCoords.length > 2"
                  :points="
                    highlightedCoords
                      .map(
                        (coord) =>
                          `${(coord.x / 100) * imageDisplayWidth},${(coord.y / 100) * imageDisplayHeight}`,
                      )
                      .join(' ')
                  "
                  fill="rgba(255, 68, 68, 0.2)"
                  @click="handleBoundingBoxClick"
                  :style="`cursor: ${isInteractionBlocked ? 'default' : 'pointer'};`"
                />

                <!-- Линии между соседними точками -->
                <path
                  v-for="(coord, index) in highlightedCoords.slice(0, -1)"
                  :key="`line-${index}`"
                  :d="`M ${(coord.x / 100) * imageDisplayWidth} ${(coord.y / 100) * imageDisplayHeight} Q ${((coord.x + highlightedCoords[index + 1].x) / 200) * imageDisplayWidth} ${((coord.y + highlightedCoords[index + 1].y) / 200) * imageDisplayHeight} ${(highlightedCoords[index + 1].x / 100) * imageDisplayWidth} ${(highlightedCoords[index + 1].y / 100) * imageDisplayHeight}`"
                  stroke="#ff4444"
                  stroke-width="3"
                  fill="none"
                  stroke-linecap="round"
                  @click="handleBoundingBoxClick"
                  :style="`cursor: ${isInteractionBlocked ? 'default' : 'pointer'};`"
                />

                <!-- Линия от последней точки к первой (замыкание контура) -->
                <path
                  v-if="highlightedCoords.length > 2"
                  :d="`M ${(highlightedCoords[highlightedCoords.length - 1].x / 100) * imageDisplayWidth} ${(highlightedCoords[highlightedCoords.length - 1].y / 100) * imageDisplayHeight} Q ${((highlightedCoords[highlightedCoords.length - 1].x + highlightedCoords[0].x) / 200) * imageDisplayWidth} ${((highlightedCoords[highlightedCoords.length - 1].y + highlightedCoords[0].y) / 200) * imageDisplayHeight} ${(highlightedCoords[0].x / 100) * imageDisplayWidth} ${(highlightedCoords[0].y / 100) * imageDisplayHeight}`"
                  stroke="#ff4444"
                  stroke-width="3"
                  fill="none"
                  stroke-linecap="round"
                  @click="handleBoundingBoxClick"
                  :style="`cursor: ${isInteractionBlocked ? 'default' : 'pointer'};`"
                />
              </g>
            </svg>
          </div>
        </div>

        <!-- Новый блок под изображением -->
        <div class="image-bottom-section">
          <div class="named-entities-container">
            <!-- <h3 class="named-entities-title">Предопределенные атрибуты</h3> -->
            <div v-if="namedEntities.length === 0" class="no-entities">
              <p
                v-if="selectedDocumentStatus === DocumentStatusesEnum.upgrading"
                class="searching-message"
              >
                Ищем предопределенные атрибуты...
              </p>
              <p v-else>Предопределенные атрибуты не найдены</p>
            </div>
            <div v-else class="entities-grid">
              <div
                v-for="(entity, index) in namedEntities"
                :key="index"
                class="entity-card"
                :class="`entity-${entity.entity_type}`"
              >
                <div class="entity-header">
                  <span class="entity-type">{{ getEntityTypeLabel(entity.entity_type) }}</span>
                </div>
                <div class="entity-value">{{ entity.entity_value }}</div>
                <div v-if="entity.details" class="entity-details">{{ entity.details }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Правая часть - текст -->
      <div class="text-section">
        <TextItem
          v-for="(item, index) in processedContent"
          :key="index"
          :text="item.text"
          :is-hovered="effectiveHoveredIndex === index"
          :is-editing="editingIndex === index"
          :is-saving="isSaving"
          @mouseenter="editingIndex === null && (hoveredIndex = index)"
          @mouseleave="editingIndex === null && (hoveredIndex = null)"
          @start-editing="startEditing(index)"
          @update:text="
            async (newText) => {
              try {
                await updateItemText(index, newText);
                finishEditing();
              } catch (error) {
                console.error('Ошибка при обновлении текста:', error);
                // Ошибка уже обработана в updateItemText
              }
            }
          "
          @cancel-editing="finishEditing()"
        />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
// Заглушка
.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 40px);
  background-color: #f8f9fa;
  border-radius: 10px;
  box-shadow: 0 0 10px 0 rgba(0, 0, 0, 0.1);
}

.placeholder-content {
  text-align: center;
  max-width: 600px;
  padding: 40px;
  cursor: default;
}

.placeholder-icon {
  width: 120px;
  height: 120px;
  margin: 0 auto 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.6;
}

.placeholder-icon-shape {
  width: 80px;
  height: 80px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: 10px;
    left: 50%;
    transform: translateX(-50%);
    width: 20px;
    height: 25px;
    background-color: #5f6368;
  }

  &::after {
    content: '';
    position: absolute;
    top: 35px;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 30px solid transparent;
    border-right: 30px solid transparent;
    border-top: 40px solid #5f6368;
  }
}

.placeholder-title {
  font-size: 24px;
  font-weight: 600;
  color: #202124;
  margin: 0 0 16px 0;
}

.placeholder-description {
  font-size: 16px;
  color: #5f6368;
  line-height: 1.5;
  margin: 0 0 40px 0;
}

.placeholder-steps {
  display: flex;
  flex-direction: column;
  gap: 20px;
  align-items: flex-start;
  width: 100%;
}

.step {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  background-color: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  width: 100%;
  cursor: default;
}

.step-number {
  width: 32px;
  height: 32px;
  background-color: #1a73e8;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
  flex-shrink: 0;
}

.step-text {
  font-size: 14px;
  color: #202124;
  font-weight: 500;
}

.content-container {
  display: flex;
  gap: 20px;
}

.image-section {
  flex: 2;
  position: relative;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 40px);
}

.image-wrapper {
  position: relative;
  width: 100%;
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f8f9fa;
  box-shadow: 0 0 10px 0 rgba(0, 0, 0, 0.1);
  height: fit-content;
  border-radius: 10px;
  overflow: hidden;
}

.image-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  cursor: default;
}

// Удаляем стили для лупы
// .magnifier {
//   position: fixed;
//   z-index: 1000;
//   border: 3px solid #1a73e8;
//   border-radius: 8px;
//   overflow: hidden;
//   box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
//   pointer-events: none;
//   background: white;
// }

// .magnifier-content {
//   width: 100%;
//   height: 100%;
//   background-repeat: no-repeat;
//   border-radius: 5px;
// }

// Индикатор загрузки
.image-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #e8eaed;
  border-top: 4px solid #1a73e8;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.loading-text {
  margin: 0;
  font-size: 16px;
  color: #5f6368;
  font-weight: 500;
}

// Ошибка загрузки
.image-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px;
  color: #ea4335;
}

.error-icon {
  font-size: 48px;
}

.error-text {
  margin: 0;
  font-size: 16px;
  color: #ea4335;
  font-weight: 500;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.connection-lines {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  right: 0;
  z-index: 5;
}

.metric-book-image {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
}

.image-bottom-section {
  flex: 1;
  background-color: #ffffff;
  border-radius: 10px;
  box-shadow: 0 0 10px 0 rgba(0, 0, 0, 0.1);
  padding: 20px;
  margin-top: 20px;
  min-height: 200px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.named-entities-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.named-entities-title {
  font-size: 18px;
  font-weight: 600;
  color: #202124;
  margin: 0 0 20px 0;
  padding-bottom: 10px;
  border-bottom: 2px solid #e8eaed;
}

.no-entities {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  color: #5f6368;
  font-style: italic;

  p {
    margin: 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  // Стили для сообщения "Ищем предопределенные атрибуты..."
  .searching-message {
    // color: #1a73e8;
    font-weight: 500;

    &::before {
      content: '';
      width: 16px;
      height: 16px;
      border: 2px solid #444444;
      border-top: 2px solid transparent;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
  }
}

.entities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 16px;
  flex: 1;
  overflow-y: auto;
  padding-right: 8px;
  margin-right: -8px;
}

.entities-grid::-webkit-scrollbar {
  width: 6px;
}

.entities-grid::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.entities-grid::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.entities-grid::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.entity-card {
  background-color: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
  border-left: 4px solid #e8eaed;
  transition: all 0.2s ease;
  cursor: default;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
}

.entity-header {
  margin-bottom: 8px;
}

.entity-type {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 4px 8px;
  border-radius: 4px;
  color: #ffffff;
}

.entity-value {
  font-size: 16px;
  font-weight: 500;
  color: #202124;
  margin-bottom: 4px;
  word-break: break-word;
}

.entity-details {
  font-size: 14px;
  color: #5f6368;
  font-style: italic;
}

// Цвета для разных типов сущностей
.entity-person .entity-type {
  background-color: #1a73e8;
}

.entity-place .entity-type {
  background-color: #34a853;
}

.entity-document .entity-type {
  background-color: #ea4335;
}

.entity-date .entity-type {
  background-color: #fbbc04;
  color: #202124;
}

.entity-organization .entity-type {
  background-color: #9c27b0;
}

.entity-event .entity-type {
  background-color: #ff9800;
}

.entity-other .entity-type {
  background-color: #6c757d;
}

.text-section {
  flex: 1;
  background-color: #ffffff;
  border-radius: 10px;
  box-shadow: 0 0 10px 0 rgba(0, 0, 0, 0.1);
  padding: 20px;
  height: calc(100vh - 40px);
  display: flex;
  flex-flow: column nowrap;
  justify-content: flex-start;
  align-items: stretch;
  align-content: flex-start;
  gap: 10px;
  overflow-y: scroll;

  .text-region {
    display: flex;
    flex-flow: column nowrap;
    gap: 10px;
  }
}

// Медиа-запросы для адаптивности
@media (max-width: 768px) {
  .content-container {
    flex-direction: column;
    gap: 16px;
  }

  .image-section {
    flex: none;
    height: auto;
  }

  .image-wrapper {
    min-height: 300px;
  }

  .text-section {
    height: auto;
    max-height: 50vh;
  }
}

@media (max-width: 480px) {
  .image-wrapper {
    min-height: 250px;
  }

  .text-section {
    max-height: 40vh;
  }
}
</style>
