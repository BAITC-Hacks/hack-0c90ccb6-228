"""Pure filtering. LLM never changes eligibility or ranking."""
import json
from pathlib import Path
from typing import Callable
from models import MatchRequest, Profile


def load_catalog(path: Path) -> list[Profile]:
    profiles = [Profile.model_validate(json.loads(line))
                for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not profiles or len({p.id for p in profiles}) != len(profiles):
        raise ValueError("Catalog is empty or contains duplicate IDs")
    return profiles


def match(profiles: list[Profile], request: MatchRequest) -> dict:
    pool = [p for p in profiles if request.category in p.categories]
    funnel = [{"key": "category", "label": "В категории", "remaining": len(pool), "excluded": 0}]
    removed = {}

    def stage(key: str, label: str, predicate: Callable[[Profile], bool]):
        nonlocal pool
        before = len(pool)
        pool = [p for p in pool if predicate(p)]
        removed[key] = before - len(pool)
        funnel.append({"key": key, "label": label, "remaining": len(pool), "excluded": removed[key]})

    stage("city", "В вашем городе", lambda p: p.city == request.city)
    city_count = len(pool)
    stage("date", "Свободны на дату", lambda p: request.event_date not in p.busy_dates)
    stage("budget", "В бюджете", lambda p: p.price_from_kzt <= request.budget)
    stage("format", "Берут формат", lambda p: request.event_format in p.event_formats)
    stage("language", "Подходит язык", lambda p: not request.language or request.language in p.languages)
    stage("duration", "Подходит время", lambda p: request.duration_hours is None
          or p.max_hours is None or p.max_hours >= request.duration_hours)
    pool.sort(key=lambda p: (request.budget - p.price_from_kzt, p.id))
    reasons = [f"заняты на {request.event_date:%d.%m.%Y}: {removed['date']}",
               f"цена выше бюджета: {removed['budget']}",
               f"не берут формат «{request.event_format}»: {removed['format']}"]
    if request.language:
        reasons.append(f"не подходит язык: {removed['language']}")
    if request.duration_hours:
        reasons.append(f"недостаточная длительность: {removed['duration']}")
    audit = "; ".join(reasons)
    if city_count == 0:
        status = "CITY_CATEGORY_NOT_FOUND"
        message = f"В городе {request.city} нет подрядчиков в категории «{request.category}»."
    elif not pool:
        status = "NO_CANDIDATES_MATCHED"
        message = f"В городе {request.city} профилей этой категории: {city_count}, но никто не прошёл условия. Отсев по порядку: {audit}."
    else:
        status = "SUCCESS"
        message = f"Подобрано: {min(3, len(pool))}. Все свободны на {request.event_date:%d.%m.%Y} и проходят ваши условия."
    partial = None
    if 0 < len(pool) < 3:
        partial = f"В подборке {len(pool)} из 3: в городе профилей этой категории — {city_count}. Отсев по порядку: {audit}."
        if city_count < 3:
            partial += " В каталоге этого города изначально меньше трёх профилей этой категории."
    return {"status": status, "message": message, "partial_reason": partial,
            "funnel": funnel, "excluded": removed, "eligible_count": len(pool),
            "city_category_count": city_count, "selected": pool[:3]}
