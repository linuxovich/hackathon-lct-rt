from pydantic import BaseModel, Field
from typing import Literal


class NamedEntity(BaseModel):
    entity_type: Literal["person", "place", "document", "date"] = Field(description="Тип именованной сущности. Если человек, то person, если место, то place, если документ, то document, если дата, то date")
    entity_value: str = Field(description="Имя, фамилия, название документа, фонд и опись или другое значение именованной сущности")
    details: str = Field(description="Дополнительная информация о сущности")


class RegionResult(BaseModel):
    corrected_text: str = Field(description="Исправленный текст ТОЛЬКО на старославянском языке. ТОЛЬКО исправленный текст, никаких дополнений.")
    named_entities: list[NamedEntity]
    confidence: float = Field(description="Уверенность в исправлении текста от 0 до 1", ge=0, le=1)


class LLMResponse(BaseModel):
    corrected_text: str = Field(description="Исправленный текст ТОЛЬКО на старославянском языке. ТОЛЬКО исправленный текст, никаких дополнений.")
    named_entities: list[NamedEntity]
    confidence: float = Field(description="Уверенность в исправлении текста от 0 до 1", ge=0, le=1)


# Модели для исправления текстов
class TextCorrectionResult(BaseModel):
    corrected_text: str = Field(description="Исправленный текст ТОЛЬКО на старославянском языке. ТОЛЬКО исправленный текст, никаких дополнений.")
    confidence: float = Field(description="Уверенность в исправлении текста от 0 до 1", ge=0, le=1)

def create_text_correction_model(region_count: int):
    """Создает модель для исправления текстов с жесткими ограничениями"""
    class TextCorrectionResponse(BaseModel):
        regions: list[TextCorrectionResult] = Field(
            description=f"Исправленные тексты для каждого региона в том же порядке, что и входные тексты. Требуется точно {region_count} регионов.",
            min_length=region_count,
            max_length=region_count
        )
    
    return TextCorrectionResponse

# Модели для извлечения именованных сущностей
class NamedEntityResult(BaseModel):
    named_entities: list[NamedEntity] = Field(description="Список именованных сущностей из текста")

def create_named_entities_model(region_count: int):
    """Создает модель для извлечения именованных сущностей с жесткими ограничениями"""
    class NamedEntitiesResponse(BaseModel):
        regions: list[NamedEntityResult] = Field(
            description=f"Именованные сущности для каждого региона в том же порядке, что и входные тексты. Требуется точно {region_count} регионов.",
            min_length=region_count,
            max_length=region_count
        )
    
    return NamedEntitiesResponse

# Модели для объединенного результата
def create_multi_region_model(region_count: int):
    """Создает модель с жесткими ограничениями на количество регионов"""
    class MultiRegionLLMResponse(BaseModel):
        regions: list[RegionResult] = Field(
            description=f"Результаты обработки для каждого региона в том же порядке, что и входные тексты. Требуется точно {region_count} регионов.",
            min_length=region_count,
            max_length=region_count
        )
    
    return MultiRegionLLMResponse

# Базовая модель для обратной совместимости
class MultiRegionLLMResponse(BaseModel):
    regions: list[RegionResult] = Field(description="Результаты обработки для каждого региона в том же порядке, что и входные тексты")
    