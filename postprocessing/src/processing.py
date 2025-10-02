from logging import getLogger

from src.llm import invoke_multi_region_agent
from src.models import MultiRegionLLMResponse


logger = getLogger(__name__)

async def process_text(data: dict) -> dict:
    if "regions" not in data:
        raise ValueError("Regions not found in data")
    
    # Собираем все тексты из регионов
    texts_to_process = []
    region_indices = []
    
    for i, obj in enumerate(data["regions"]):
        concatenated_text = obj.get("concatenated_text", "")
        if concatenated_text:
            texts_to_process.append(concatenated_text)
            region_indices.append(i)
        else:
            # Для пустых текстов сразу устанавливаем пустые значения
            obj["corrected_text"] = ""
            obj["named_entities"] = []
            obj["confidence"] = 0
    
    # Если есть тексты для обработки, отправляем их все одним запросом
    if texts_to_process:
        logger.info(f"Processing {len(texts_to_process)} texts in batch")
        response: MultiRegionLLMResponse = await invoke_multi_region_agent(texts_to_process)
        logger.info(f"Response received for {len(response.regions)} regions")
        
        # Распределяем результаты обратно по регионам
        for i, region_result in enumerate(response.regions):
            region_index = region_indices[i]
            data["regions"][region_index]["corrected_text"] = region_result.corrected_text
            data["regions"][region_index]["named_entities"] = [entity.model_dump() for entity in region_result.named_entities]
            data["regions"][region_index]["confidence"] = region_result.confidence

    return data