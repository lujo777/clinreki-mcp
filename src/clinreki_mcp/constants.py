"""Константы и проверенные опытным путём параметры API apicr.minzdrav.gov.ru."""

# Базовый адрес и единственный endpoint (операция задаётся параметром ?op=).
BASE_URL = "https://apicr.minzdrav.gov.ru"
API_PATH = "/api.ashx"

# Имена операций.
OP_SEARCH = "GetJsonClinrecsFilterV2"  # POST: поиск/список КР
OP_DOCUMENT = "GetClinrec2"            # GET:  полный документ одной КР
OP_MKB = "GetMkbRefList"               # GET:  справочник МКБ-10 (дерево, ~3.2 МБ)
OP_NKO = "GetNkoList"                  # GET:  список разработчиков (НКО)

# Сопоставление дружелюбных значений возраста с кодами фильтра agecategory.
AGE_CATEGORY = {"adult": 1, "child": 2, "both": 3}

# Ограничители размеров (защита контекста модели).
MAX_PAGE_SIZE = 50              # максимальный размер страницы поиска
ALL_RECORDS_PAGE_SIZE = 2000   # весь список (1798 записей) помещается в один запрос
DEFAULT_SECTION_CHARS = 8000   # сколько символов раздела отдавать по умолчанию
MAX_SECTION_CHARS = 50000      # жёсткий потолок на один ответ с текстом
