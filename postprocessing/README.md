# ML Postprocessing Pipeline

Сервис постпроцессинга распознанного текста
Основные функции сервиса:
1. Выделение именованных сущностей
    - Люди
    - Места
    - Даты
    - Документы
2. Коррекция текста

---

## Используемые технологии
1. API Сервис
    - [python](https://docs.python.org)
    - [langchain](https://python.langchain.com/docs/introduction/)
    - [aiohttp](https://docs.aiohttp.org/en/stable/)
    - [pydantic](https://docs.pydantic.dev/latest/)
2. LLM Модель
    - [Ollama](https://docs.ollama.com/)
    - [Gigachat](https://huggingface.co/ai-sage/GigaChat-20B-A3B-instruct-v1.5)


## Схема работы
        
Постпроцессинг состоит из двух компонентов - веб-сервера и LLM.\
При обращении сервер требует два параметра - пути до входных и выходных файлов. 

После сервис находит все json-файлы в указанной директории и поэтапно обрабатывает каждый объект.

При обработке файла извлекаются распозданные блоки текста, из которых сервис достает распозданные текст, соединенный по строкам. После обхода файла создается pydantic модель и отправляется запрос в LLM с определенным промтом и структурированным ответом. На выходе из LLM мы получаем исправленный текст.

После корректировки текста сервис делает запрос в LLM на распознавание именнованных сущностей. При получении ответа от нейросети, обновляет json и сохраняет его по указанному пути. 

После обработки всех файлов делается запрос на бекенд с уведомлением об успешном завершении процесса постобработки.

[![](https://img.plantuml.biz/plantuml/svg/hP9DRW8n38NtSmgls7415XM7O3yoYPa9v4-EG-7sEFntEcgxw2QoxEyzFJbU5q6M6dptITk-41-9OVa1-v9YdpaPAYKnhC35N0KMaAgq8gECfPjGSxfxJHQ4JZAZy3xq1hqdVeFxA_mQVGNLTfSue8ZQgYPaWGayk07DY79Bq805vBF5ACv0I9PyzqIctYOnav57v5zJa7scq0P432gbA6TnLFunru_6tnPVistHG5_yoqSLF2fzRU-Sfnd9suMiOCEL9ZUpHNEWQ7KuYcHesRgrDjfrNG00)](https://editor.plantuml.com/uml/hP9DRW8n38NtSmgls7415XM7O3yoYPa9v4-EG-7sEFntEcgxw2QoxEyzFJbU5q6M6dptITk-41-9OVa1-v9YdpaPAYKnhC35N0KMaAgq8gECfPjGSxfxJHQ4JZAZy3xq1hqdVeFxA_mQVGNLTfSue8ZQgYPaWGayk07DY79Bq805vBF5ACv0I9PyzqIctYOnav57v5zJa7scq0P432gbA6TnLFunru_6tnPVistHG5_yoqSLF2fzRU-Sfnd9suMiOCEL9ZUpHNEWQ7KuYcHesRgrDjfrNG00)

