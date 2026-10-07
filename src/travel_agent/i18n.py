"""Three languages: English, French and Russian. Detection of the traveller's language, names, dates, money, texts.

No translation model is involved: every sentence is a template written by hand, filled with the agent's numbers.
The data itself (hotel brochures, activity names) is in French and is shown as it is.
"""

from __future__ import annotations

import re
from datetime import date

LANGUAGES = {"en": "English", "fr": "Français", "ru": "Русский"}
DEFAULT_LANGUAGE = "en"

# --------------------------------------------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------------------------------------------

_FRENCH = {"le", "la", "les", "un", "une", "des", "du", "de", "et", "avec", "pour", "je", "nous", "on", "dans", "au",
           "aux", "est", "très", "pas", "sans", "mais", "ou", "un", "hôtel", "piscine", "famille", "enfants", "calme",
           "ville", "soir", "fête", "plage", "proche", "près", "centre", "vacances", "veux", "voudrais", "cherche",
           "aime", "aimons", "amoureux", "romantique", "visites", "musées", "luxe", "pas", "cher", "chambre", "vue"}
_ENGLISH = {"the", "a", "an", "and", "with", "for", "i", "we", "in", "to", "of", "near", "but", "or", "hotel", "pool",
            "swimming", "family", "kids", "children", "quiet", "city", "night", "party", "beach", "close", "center",
            "centre", "holiday", "want", "would", "like", "looking", "love", "romantic", "couple", "museums",
            "sightseeing", "luxury", "cheap", "room", "view", "some", "our", "my"}
_ACCENTED = re.compile(r"[àâçéèêëîïôûùüÿœ]")
_CYRILLIC = re.compile(r"[а-яё]")


def detect_language(text: str) -> str | None:
    """Guess whether `text` is English, French or Russian; None when there is no clear sign.

    Cyrillic letters mean Russian. Between English and French, common words count one point each and words with a
    French accent one more point for French. A short wish rarely leaves any doubt; when it does, the caller keeps
    the language it already uses.
    """
    text = text.lower()
    letters = re.findall(r"[^\W\d_]", text)
    if not letters:
        return None
    if sum(bool(_CYRILLIC.match(c)) for c in letters) / len(letters) > 0.3:
        return "ru"
    words = re.findall(r"[^\W\d_]+", text)
    french = sum(w in _FRENCH for w in words) + sum(bool(_ACCENTED.search(w)) for w in words)
    english = sum(w in _ENGLISH for w in words)
    if french > english:
        return "fr"
    if english > french:
        return "en"
    return None


# --------------------------------------------------------------------------------------------------------------
# Names, dates, numbers
# --------------------------------------------------------------------------------------------------------------

CITY_NAMES = {  # keys as written in the database
    "Amsterdam": {"en": "Amsterdam", "fr": "Amsterdam", "ru": "Амстердам"},
    "Athenes": {"en": "Athens", "fr": "Athènes", "ru": "Афины"},
    "Barcelone": {"en": "Barcelona", "fr": "Barcelone", "ru": "Барселона"},
    "Berlin": {"en": "Berlin", "fr": "Berlin", "ru": "Берлин"},
    "Budapest": {"en": "Budapest", "fr": "Budapest", "ru": "Будапешт"},
    "Dubrovnik": {"en": "Dubrovnik", "fr": "Dubrovnik", "ru": "Дубровник"},
    "Lisbonne": {"en": "Lisbon", "fr": "Lisbonne", "ru": "Лиссабон"},
    "Madrid": {"en": "Madrid", "fr": "Madrid", "ru": "Мадрид"},
    "Naples": {"en": "Naples", "fr": "Naples", "ru": "Неаполь"},
    "Porto": {"en": "Porto", "fr": "Porto", "ru": "Порту"},
    "Prague": {"en": "Prague", "fr": "Prague", "ru": "Прага"},
    "Rome": {"en": "Rome", "fr": "Rome", "ru": "Рим"},
    "Seville": {"en": "Seville", "fr": "Séville", "ru": "Севилья"},
    "Venise": {"en": "Venice", "fr": "Venise", "ru": "Венеция"},
    "Vienne": {"en": "Vienna", "fr": "Vienne", "ru": "Вена"},
}
ORIGIN_NAMES = {"Nice": {"ru": "Ницца"}, "Paris CDG": {"ru": "Париж (CDG)"}}
CATEGORY_NAMES = {
    "culture": {"en": "culture", "fr": "culture", "ru": "культура"},
    "plein air": {"en": "outdoors", "fr": "plein air", "ru": "на свежем воздухе"},
    "gastronomie": {"en": "food", "fr": "gastronomie", "ru": "гастрономия"},
    "nocturne": {"en": "nightlife", "fr": "nocturne", "ru": "вечерняя программа"},
}
_MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
           "novembre", "décembre"],
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
           "ноября", "декабря"],
}
_UNITS = {  # singular / plural, and for Russian: one / few / many
    "night": {"en": ("night", "nights"), "fr": ("nuit", "nuits"), "ru": ("ночь", "ночи", "ночей")},
    "traveller": {"en": ("traveller", "travellers"), "fr": ("voyageur", "voyageurs"),
                  "ru": ("путешественник", "путешественника", "путешественников")},
    "activity": {"en": ("activity", "activities"), "fr": ("activité", "activités"),
                 "ru": ("занятие", "занятия", "занятий")},
    "review": {"en": ("review", "reviews"), "fr": ("avis", "avis"), "ru": ("отзыв", "отзыва", "отзывов")},
    "seat": {"en": ("seat", "seats"), "fr": ("place", "places"), "ru": ("место", "места", "мест")},
}


def city_name(key: str, lang: str) -> str:
    return CITY_NAMES.get(key, {}).get(lang, key)


def city_key(name: str) -> str | None:
    """The database key of a city written in any of the three languages ("Barcelona", "Barcelone", "Барселона")."""
    wanted = name.strip().casefold()
    for key, names in CITY_NAMES.items():
        if wanted == key.casefold() or wanted in (n.casefold() for n in names.values()):
            return key
    return None


def origin_name(name: str, lang: str) -> str:
    return ORIGIN_NAMES.get(name, {}).get(lang, name)


def category_name(name: str, lang: str) -> str:
    return CATEGORY_NAMES.get(name, {}).get(lang, name)


def count(n: int, unit: str, lang: str) -> str:
    """'1 night', '4 nights', '4 nuits', '4 ночи', '5 ночей'..."""
    forms = _UNITS[unit][lang]
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            form = forms[0]
        elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            form = forms[1]
        else:
            form = forms[2]
    elif lang == "fr":
        form = forms[0] if n <= 1 else forms[1]
    else:
        form = forms[0] if n == 1 else forms[1]
    return f"{n} {form}"


def day_label(day: str | date, lang: str) -> str:
    """'Aug 12', '12 août', '12 августа'."""
    d = date.fromisoformat(day) if isinstance(day, str) else day
    month = _MONTHS[lang][d.month - 1]
    return f"{month} {d.day}" if lang == "en" else f"{d.day} {month}"


def money(amount: float, lang: str) -> str:
    """'€732' in English, '732 €' in French and Russian."""
    return f"€{amount:.0f}" if lang == "en" else f"{amount:.0f} €"


def number(value: float, lang: str, decimals: int = 1) -> str:
    """A decimal number with the decimal comma in French and Russian."""
    text = f"{value:.{decimals}f}"
    return text if lang == "en" else text.replace(".", ",")


# --------------------------------------------------------------------------------------------------------------
# Texts
# --------------------------------------------------------------------------------------------------------------

TEXT = {
    # The agent's log
    "removed_activity": {
        "en": "I removed “{name}” ({price}).",
        "fr": "J'ai retiré « {name} » ({price}).",
        "ru": "Убрано из программы: «{name}» ({price}).",
    },
    "changed_hotel": {
        "en": "{old} was still too expensive, I took {new} instead.",
        "fr": "{old} restait trop cher, j'ai pris {new} à la place.",
        "ru": "Отель {old} всё ещё не укладывался в бюджет, выбран отель {new}.",
    },
    "restored_activities": {
        "en": "With the cheaper hotel, I put back {names} ({price}).",
        "fr": "Avec l'hôtel moins cher, j'ai remis au programme {names} ({price}).",
        "ru": "С более дешёвым отелем в программу возвращено: {names} ({price}).",
    },
    "gave_up": {
        "en": "There was nothing left to give up for a departure on {day}.",
        "fr": "Je n'avais plus rien à sacrifier pour un départ le {day}.",
        "ru": "Для вылета {day} больше нечего убрать.",
    },
    "no_flight_or_hotel": {
        "en": "No flight or no hotel available for this destination on {day}.",
        "fr": "Aucun vol ou aucun hôtel disponible pour cette destination le {day}.",
        "ru": "На {day} нет подходящего рейса или отеля в этом городе.",
    },
    "other_day_possible": {
        "en": "However, leaving on {day}, a trip at {total} per person would fit.",
        "fr": "En revanche, en partant le {day}, un voyage à {total} par personne devenait possible.",
        "ru": "Зато при вылете {day} поездка за {total} на человека укладывается в бюджет.",
    },
    "other_day_more_activities": {
        "en": "By the way, leaving on {day} you would keep {kept} instead of {instead_of}, for {total}.",
        "fr": "Au passage, en partant le {day} vous gardiez {kept} au lieu de {instead_of}, pour {total}.",
        "ru": "Кстати, при вылете {day} в программе осталось бы {kept} вместо {instead_of}, за {total}.",
    },
    "other_day_cheaper": {
        "en": "By the way, leaving on {day} the same trip would cost {total}, {saving} less per person.",
        "fr": "Au passage, en partant le {day} le même programme revenait à {total}, soit {saving} de moins par personne.",
        "ru": "Кстати, при вылете {day} та же поездка стоила бы {total}, на {saving} дешевле на человека.",
    },
    # The summary of a trip
    "summary_flight": {
        "en": "Flight {flight} from {origin} on {day} at {time} ({hours} h): {price}.",
        "fr": "Vol {flight} au départ de {origin} le {day} à {time} ({hours} h) : {price}.",
        "ru": "Рейс {flight}: {origin}, {day} в {time} ({hours} ч), {price}.",
    },
    "summary_hotel": {
        "en": "Hotel: {hotel}, {nights} at {price} per night.",
        "fr": "Hôtel : {hotel}, {nights} à {price} la nuit.",
        "ru": "Отель: {hotel}, {nights} по {price} за ночь.",
    },
    "summary_activities": {"en": "Activities: {names}.", "fr": "Au programme : {names}.", "ru": "В программе: {names}."},
    "summary_no_activity": {"en": "No activities.", "fr": "Aucune activité.", "ru": "Без занятий."},
    "summary_total": {
        "en": "All in, {total} per person, for a budget of {budget}.",
        "fr": "Le tout revient à {total} par personne, pour un budget de {budget}.",
        "ru": "Итого {total} на человека при бюджете {budget}.",
    },
    "summary_nothing": {
        "en": "I found nothing that fits this budget.",
        "fr": "Je n'ai rien trouvé qui rentre dans ce budget.",
        "ru": "Ничего не уложилось в этот бюджет.",
    },
    "hint_nothing": {
        "en": "Raise the budget, shorten the stay or try other dates: flight prices change a lot from one day to the next.",
        "fr": "Augmentez le budget, réduisez le séjour ou essayez d'autres dates : le prix des vols change beaucoup d'un jour à l'autre.",
        "ru": "Увеличьте бюджет, сократите поездку или попробуйте другие даты: цены на билеты сильно меняются день ото дня.",
    },
    # Booking
    "nothing_to_book": {
        "en": "Nothing to book: no trip was found.",
        "fr": "Rien à réserver : aucun voyage n'a été trouvé.",
        "ru": "Нечего бронировать: поездка не найдена.",
    },
    "needs_confirmation": {
        "en": "Nothing has been booked yet. The trip to {city} would cost {total} per person, {total_all} in all. "
              "Confirm to record the booking.",
        "fr": "Rien n'a été réservé. Le voyage à {city} coûterait {total} par personne, soit {total_all} au total. "
              "Il faut confirmer pour que la réservation soit enregistrée.",
        "ru": "Пока ничего не забронировано. Поездка ({city}) обойдётся в {total} на человека, всего {total_all}. "
              "Подтвердите, чтобы бронирование было записано.",
    },
    "booked": {
        "en": "Booked for {client}: {city}, {nights}, {total_all} in all.",
        "fr": "C'est réservé pour {client} : {city}, {nights}, {total_all} au total.",
        "ru": "Забронировано на имя {client}: {city}, {nights}, всего {total_all}.",
    },
    "already_booked": {
        "en": "{client} has already booked this trip: nothing was booked twice.",
        "fr": "{client} a déjà réservé ce voyage : rien n'a été réservé une seconde fois.",
        "ru": "Эта поездка уже забронирована на имя {client}: повторной брони не будет.",
    },
    "no_seats": {
        "en": "Flight {flight} no longer has {seats} left: nothing was booked. Please search again.",
        "fr": "Le vol {flight} n'a plus {seats} libres : rien n'a été réservé. Relancez la recherche.",
        "ru": "На рейсе {flight} больше нет нужного числа мест ({seats}): бронирование не выполнено. Повторите поиск.",
    },
    # Interface
    "page_title": {"en": "Travel agent", "fr": "Agent de voyage", "ru": "Турагент"},
    "title": {"en": "Where are you going?", "fr": "Où partez-vous ?", "ru": "Куда поедем?"},
    "caption": {
        "en": "An agent that searches, compares, makes trade-offs when the budget is short, and tells you what it gave up.",
        "fr": "Un agent qui cherche, compare, arbitre quand le budget ne suit pas, et vous dit ce qu'il a sacrifié.",
        "ru": "Агент ищет, сравнивает, идёт на компромиссы, когда не хватает бюджета, и говорит, от чего пришлось отказаться.",
    },
    "settings": {"en": "Settings", "fr": "Réglages", "ru": "Настройки"},
    "loading": {
        "en": "Loading the sentence encoder and reading the hotel brochures (once)…",
        "fr": "Chargement du modèle d'embeddings et lecture des brochures (une seule fois)…",
        "ru": "Загрузка модели и чтение буклетов отелей (один раз)…",
    },
    "language": {"en": "Language", "fr": "Langue", "ru": "Язык"},
    "auto": {"en": "Automatic", "fr": "Automatique", "ru": "Автоматически"},
    "language_help": {
        "en": "Automatic: the agent answers in the language of your wish (English, French or Russian).",
        "fr": "Automatique : l'agent répond dans la langue de votre demande (anglais, français ou russe).",
        "ru": "Автоматически: агент отвечает на языке вашего запроса (английский, французский или русский).",
    },
    "restore": {
        "en": "Put activities back after a cheaper hotel",
        "fr": "Remettre des sorties après un hôtel moins cher",
        "ru": "Возвращать занятия после более дешёвого отеля",
    },
    "restore_help": {
        "en": "Off: the agent keeps the bare programme it had accepted for the dearer hotel, as in the original version.",
        "fr": "Désactivé : l'agent garde le programme réduit accepté pour l'hôtel plus cher, comme dans la version d'origine.",
        "ru": "Выключено: агент оставляет урезанную программу, принятую для более дорогого отеля, как в исходной версии.",
    },
    "destination": {"en": "Destination", "fr": "Destination", "ru": "Город"},
    "travellers": {"en": "Travellers", "fr": "Voyageurs", "ru": "Человек"},
    "dates": {"en": "Dates", "fr": "Dates du séjour", "ru": "Даты поездки"},
    "dates_help": {
        "en": "Pick the departure day, then the return day.",
        "fr": "Choisissez la date d'aller, puis celle du retour.",
        "ru": "Выберите дату вылета, затем дату возвращения.",
    },
    "budget": {
        "en": "Budget per person, everything included (€)",
        "fr": "Budget par personne, tout compris (€)",
        "ru": "Бюджет на человека, всё включено (€)",
    },
    "wish": {"en": "What are you looking for?", "fr": "Ce que vous recherchez", "ru": "Что вы ищете?"},
    "wish_help": {
        "en": "Write freely, in English, French or Russian: a sentence encoder compares the meaning of your words with "
              "the hotel brochures, it is not a keyword search.",
        "fr": "Écrivez librement, en français, anglais ou russe : un modèle d'embeddings compare le sens de votre phrase "
              "aux brochures des hôtels, ce n'est pas une recherche par mots-clés.",
        "ru": "Пишите свободно, по-русски, по-английски или по-французски: модель сравнивает смысл вашей фразы с "
              "буклетами отелей, это не поиск по ключевым словам.",
    },
    "example_wish": {
        "en": "a family hotel with a pool, and sightseeing in the city",
        "fr": "un hôtel pour la famille avec une piscine, et des visites dans la ville",
        "ru": "семейный отель с бассейном и экскурсии по городу",
    },
    "search": {"en": "Search", "fr": "Rechercher", "ru": "Искать"},
    "pick_return": {
        "en": "Pick a return day in the calendar too.",
        "fr": "Choisissez aussi une date de retour dans le calendrier.",
        "ru": "Выберите в календаре и дату возвращения.",
    },
    "return_after": {
        "en": "The return must be at least one day after the departure.",
        "fr": "Le retour doit tomber au moins un jour après le départ.",
        "ru": "Дата возвращения должна быть хотя бы на день позже вылета.",
    },
    "fill_form": {
        "en": "Fill in the form above, then click **Search**.",
        "fr": "Remplissez le formulaire ci-dessus, puis cliquez sur **Rechercher**.",
        "ru": "Заполните форму выше и нажмите **Искать**.",
    },
    "no_trip": {
        "en": "**No trip possible to {city} with {budget} per person.**",
        "fr": "**Aucun voyage possible à {city} avec {budget} par personne.**",
        "ru": "**Поездка ({city}) с бюджетом {budget} на человека невозможна.**",
    },
    "tried": {
        "en": "Everything the agent tried before giving up:",
        "fr": "Tout ce que l'agent a essayé avant d'abandonner :",
        "ru": "Всё, что агент попробовал, прежде чем сдаться:",
    },
    "trip_title": {"en": "{city}, {start} – {end}", "fr": "{city}, du {start} au {end}", "ru": "{city}, {start} – {end}"},
    "flight": {"en": "Flight", "fr": "Vol", "ru": "Перелёт"},
    "hotel": {"en": "Hotel", "fr": "Hôtel", "ru": "Отель"},
    "per_night": {"en": "{price} per night", "fr": "{price} la nuit", "ru": "{price} за ночь"},
    "activities": {"en": "Activities", "fr": "Activités", "ru": "Занятия"},
    "total": {"en": "Total per person", "fr": "Total par personne", "ru": "Итого на человека"},
    "vs_budget": {"en": "{delta} vs budget", "fr": "{delta} vs budget", "ru": "{delta} к бюджету"},
    "for_everyone": {
        "en": "That is **{total}** for {travellers}.",
        "fr": "Soit **{total}** pour {travellers}.",
        "ru": "Всего за всех: **{total}** ({travellers}).",
    },
    "log_title": {
        "en": "**What I did, and what I noticed:**",
        "fr": "**Ce que j'ai fait, et ce que j'ai remarqué :**",
        "ru": "**Что было сделано и что замечено:**",
    },
    "all_fit": {
        "en": "Everything fitted in the budget, I had nothing to give up.",
        "fr": "Tout rentrait dans le budget, je n'ai rien eu à sacrifier.",
        "ru": "Всё уложилось в бюджет, ни от чего не пришлось отказываться.",
    },
    "relevance": {"en": "relevance {score}", "fr": "pertinence {score}", "ru": "релевантность {score}"},
    "brochure": {
        "en": "Brochure (in French, as provided by the hotel)",
        "fr": "Brochure de l'hôtel",
        "ru": "Буклет отеля (на французском)",
    },
    "programme": {"en": "Your programme", "fr": "Votre programme", "ru": "Ваша программа"},
    "activity_line": {
        "en": "**{name}** ({category}): {hours} h, {price}",
        "fr": "**{name}** ({category}) : {hours} h, {price}",
        "ru": "**{name}** ({category}): {hours} ч, {price}",
    },
    "no_activity": {
        "en": "_No activity: the budget did not allow any._",
        "fr": "_Aucune activité : le budget ne le permettait pas._",
        "ru": "_Без занятий: бюджет не позволил._",
    },
    "your_flight": {"en": "Your flight", "fr": "Le vol retenu", "ru": "Ваш рейс"},
    "flight_line": {
        "en": "**{flight}** · {origin} → {city} · {day} at {time} · {hours} h",
        "fr": "**{flight}** · {origin} → {city} · le {day} à {time} · {hours} h",
        "ru": "**{flight}** · {origin} → {city} · {day} в {time} · {hours} ч",
    },
    "consulted": {
        "en": "See what the agent looked at before deciding",
        "fr": "Voir ce que l'agent a consulté avant de décider",
        "ru": "Что агент изучил перед решением",
    },
    "flights_that_day": {
        "en": "**Flights available that day**",
        "fr": "**Les vols disponibles ce jour-là**",
        "ru": "**Рейсы на этот день**",
    },
    "closest_hotels": {
        "en": "**The hotels closest to your wish**",
        "fr": "**Les hôtels les plus proches de votre demande**",
        "ru": "**Отели, ближе всего к вашему запросу**",
    },
    "attempts": {
        "en": "**Every combination it priced** (requested day, then the neighbouring days)",
        "fr": "**Chaque combinaison chiffrée** (le jour demandé, puis les jours voisins)",
        "ru": "**Все рассчитанные варианты** (запрошенный день, затем соседние дни)",
    },
    "col_day": {"en": "Day", "fr": "Jour", "ru": "День"},
    "col_hotel": {"en": "Hotel", "fr": "Hôtel", "ru": "Отель"},
    "col_flight": {"en": "Flight", "fr": "Vol", "ru": "Рейс"},
    "col_nights": {"en": "Hotel (all nights)", "fr": "Hôtel (toutes les nuits)", "ru": "Отель (все ночи)"},
    "col_activities": {"en": "Activities", "fr": "Activités", "ru": "Занятия"},
    "col_total": {"en": "Total", "fr": "Total", "ru": "Итого"},
    "col_verdict": {"en": "Verdict", "fr": "Verdict", "ru": "Итог"},
    "col_origin": {"en": "From", "fr": "Départ", "ru": "Откуда"},
    "col_time": {"en": "Time", "fr": "Heure", "ru": "Время"},
    "col_hours": {"en": "Hours", "fr": "Durée (h)", "ru": "Часы"},
    "col_price": {"en": "Price (€)", "fr": "Prix (€)", "ru": "Цена (€)"},
    "col_seats": {"en": "Seats left", "fr": "Places", "ru": "Мест"},
    "col_stars": {"en": "Stars", "fr": "Étoiles", "ru": "Звёзды"},
    "col_rating": {"en": "Rating", "fr": "Note", "ru": "Оценка"},
    "col_night": {"en": "Per night (€)", "fr": "Par nuit (€)", "ru": "За ночь (€)"},
    "col_score": {"en": "Relevance", "fr": "Pertinence", "ru": "Релевантность"},
    "fits": {"en": "fits", "fr": "OK", "ru": "подходит"},
    "over": {"en": "over by {amount}", "fr": "dépasse de {amount}", "ru": "дороже на {amount}"},
    "book_title": {"en": "Book", "fr": "Réserver", "ru": "Бронирование"},
    "name": {"en": "Name for the booking", "fr": "À quel nom ?", "ru": "На чьё имя?"},
    "name_placeholder": {"en": "Your name", "fr": "Votre nom", "ru": "Ваше имя"},
    "book_button": {"en": "Book this trip", "fr": "Réserver ce voyage", "ru": "Забронировать"},
    "name_first": {"en": "Enter a name first.", "fr": "Indiquez d'abord un nom.", "ru": "Сначала укажите имя."},
    "confirm_button": {"en": "Yes, I confirm", "fr": "Oui, je confirme", "ru": "Да, подтверждаю"},
    "data_caption": {
        "en": "Flights, hotels and activities are fictional data: do not plan real holidays with them.",
        "fr": "Vols, hôtels et activités sont des données fictives : ne préparez pas de vraies vacances avec.",
        "ru": "Рейсы, отели и занятия — вымышленные данные: не планируйте по ним настоящий отпуск.",
    },
}


def t(key: str, lang: str, **values) -> str:
    """The text `key` in `lang`, filled with `values`."""
    return TEXT[key][lang].format(**values)
