import aiofiles
from langchain_ollama import ChatOllama
from src.models import (
    LLMResponse, MultiRegionLLMResponse, 
    create_multi_region_model, create_text_correction_model, create_named_entities_model
)
from src.settings import settings
from logging import getLogger


logger = getLogger(__name__)


model = ChatOllama(model=settings.llm.model, base_url=settings.llm.base_url, temperature=0.2)
model = model.with_structured_output(LLMResponse)

async def invoke_agent(text: str) -> LLMResponse:
    async with aiofiles.open("src/prompt.txt", "r") as f:
        prompt = await f.read()
    return await model.ainvoke(prompt.format(question=text))

async def correct_texts(texts: list[str]):
    """Исправляет тексты из всех регионов"""
    async with aiofiles.open("src/region_correction.txt", "r") as f:
        prompt = await f.read()
    
    # Создаем динамическую модель для исправления текстов
    TextCorrectionModel = create_text_correction_model(len(texts))
    logger.info(f"TextCorrectionModel: {TextCorrectionModel}")
    correction_model = ChatOllama(model=settings.llm.model, base_url=settings.llm.base_url, temperature=0.2, num_thread=16, num_batch=1024, num_ctx=8192) 
    correction_model = correction_model.with_structured_output(TextCorrectionModel)
    
    # Создаем нумерованный список текстов для промпта
    texts_for_prompt = "\n".join([f"{i+1}. {text}" for i, text in enumerate(texts)])
    result = await correction_model.ainvoke(prompt.format(texts=texts_for_prompt, count=len(texts)))
    logger.info(f"Text correction result: {result}")
    return result

async def extract_named_entities(texts: list[str]):
    """Извлекает именованные сущности из исправленных текстов"""
    async with aiofiles.open("src/named_entities.txt", "r") as f:
        prompt = await f.read()
    
    # Создаем динамическую модель для извлечения сущностей
    NamedEntitiesModel = create_named_entities_model(len(texts))
    logger.info(f"NamedEntitiesModel: {NamedEntitiesModel}")
    entities_model = ChatOllama(model=settings.llm.model, base_url=settings.llm.base_url, temperature=0.6, num_thread=16, num_batch=1024, num_ctx=8192)
    entities_model = entities_model.with_structured_output(NamedEntitiesModel)
    
    # Создаем нумерованный список текстов для промпта
    texts_for_prompt = "\n".join([f"{i+1}. {text}" for i, text in enumerate(texts)])
    result = await entities_model.ainvoke(prompt.format(texts=texts_for_prompt))
    logger.info(f"Named entities result: {result}")
    return result

async def invoke_multi_region_agent(texts: list[str]) -> MultiRegionLLMResponse:
    """Старая функция для обратной совместимости - теперь использует двухэтапную обработку"""
    # Этап 1: Исправление текстов
    correction_result = await correct_texts(texts)
    
    # Извлекаем исправленные тексты
    corrected_texts = [region.corrected_text for region in correction_result.regions]
    
    # Этап 2: Извлечение именованных сущностей
    entities_result = await extract_named_entities(corrected_texts)
    
    # Объединяем результаты
    combined_regions = []
    for i in range(len(texts)):
        combined_regions.append({
            "corrected_text": correction_result.regions[i].corrected_text,
            "named_entities": [entity.model_dump() for entity in entities_result.regions[i].named_entities],
            "confidence": correction_result.regions[i].confidence
        })
    
    # Создаем результат в старом формате
    from src.models import RegionResult, NamedEntity
    regions = []
    for region_data in combined_regions:
        named_entities = [NamedEntity(**entity) for entity in region_data["named_entities"]]
        regions.append(RegionResult(
            corrected_text=region_data["corrected_text"],
            named_entities=named_entities,
            confidence=region_data["confidence"]
        ))
    
    return MultiRegionLLMResponse(regions=regions)