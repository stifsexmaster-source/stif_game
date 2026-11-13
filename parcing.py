import requests
import json
import time

def update_all_items():
    print("Начинаем сбор ВСЕХ страниц с so-wiki.ru...")
    api_url = "https://so-wiki.ru/w/api.php"
    
    # Параметры для получения списка всех страниц
    params = {
        "action": "query",
        "list": "allpages",
        "aplimit": "max", # Максимальное количество за раз (обычно 500)
        "format": "json"
    }
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StayOutParser/1.0"}
    all_items = set()
    apcontinue = None
    
    # Список слов, которые означают, что это не предмет, а служебная страница
    ignore_keywords = ["Категория:", "Шаблон:", "Файл:", "Служебная:", "Обсуждение:", "Участник:", "Википедия:", "Модуль:"]

    while True:
        if apcontinue:
            params["apcontinue"] = apcontinue

        try:
            response = requests.get(api_url, params=params, headers=headers, timeout=15)
            data = response.json()
            
            if "error" in data:
                print(f"Ошибка API: {data['error']}")
                break
                
            pages = data.get("query", {}).get("allpages", [])
            for page in pages:
                title = page["title"]
                # Проверяем, что это не служебная страница
                if not any(title.startswith(kw) for kw in ignore_keywords):
                    # Проверяем, что это не пустая страница и не слишком длинное название
                    if len(title) > 1:
                        all_items.add(title)
                        
            # Проверяем, есть ли следующая страница
            if "continue" in data:
                apcontinue = data["continue"]["apcontinue"]
                print(f"Загружено {len(all_items)} предметов... (продолжаем)")
                time.sleep(0.1) # Пауза, чтобы не забанили
            else:
                break
                
        except Exception as e:
            print(f"Ошибка сети: {e}")
            break

    if not all_items:
        print("\n[ВНИМАНИЕ] Не удалось скачать предметы. Проверьте интернет или доступ к сайту.")
        return

    sorted_items = sorted(list(all_items))
    
    with open('items.json', 'w', encoding='utf-8') as f:
        json.dump(sorted_items, f, ensure_ascii=False, indent=4)
        
    print(f"\nУспешно! Сохранено {len(sorted_items)} предметов в items.json")

if __name__ == "__main__":
    update_all_items()