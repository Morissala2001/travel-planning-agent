"""Web app: fill in a trip request, read the agent's proposal and what it gave up, then book it after confirming.

    uv run streamlit run app.py

The interface and the answers follow the language of the wish (English, French or Russian), or the one chosen at
the top of the page. TRAVEL_AGENT_DB and TRAVEL_AGENT_BROCHURES point to other data, for instance a copy.
"""

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from travel_agent import tools
from travel_agent.booking import book
from travel_agent.data import DEFAULT_BROCHURES, DEFAULT_DB, cities, connect, date_range, load_brochures
from travel_agent.i18n import (DEFAULT_LANGUAGE, LANGUAGES, TEXT, category_name, city_name, count, day_label,
                               detect_language, money, number, origin_name, t)
from travel_agent.planner import Request, TravelAgent
from travel_agent.render import booking_text, log_lines, trip_title, verdict

DB = Path(os.environ.get("TRAVEL_AGENT_DB", DEFAULT_DB))
BROCHURES = Path(os.environ.get("TRAVEL_AGENT_BROCHURES", DEFAULT_BROCHURES))
EXAMPLES = TEXT["example_wish"]

st.set_page_config(page_title="Travel agent", page_icon=":material/luggage:", layout="wide")


@st.cache_resource(show_spinner=False)
def hotel_search(folder: str) -> tools.HotelSearch:
    return tools.HotelSearch(load_brochures(folder), tools.load_encoder())


def browser_language() -> str:
    locale = (st.context.locale or "").split("-")[0].lower()
    return locale if locale in LANGUAGES else DEFAULT_LANGUAGE


# --------------------------------------------------------------------------------------------------------------
# Language: chosen at the top of the page, or "auto" = the language of the last wish (the browser's at first).
# --------------------------------------------------------------------------------------------------------------
choice = st.session_state.get("language") or "auto"
lang = choice if choice != "auto" else st.session_state.get("detected") or browser_language()

st.title(t("title", lang))
st.caption(t("caption", lang))
st.segmented_control("Language · Langue · Язык", ["auto", *LANGUAGES], key="language", default="auto",
                     format_func=lambda code: t("auto", lang) if code == "auto" else code.upper(),
                     help=t("language_help", lang), label_visibility="collapsed")

with st.sidebar:
    st.header(t("settings", lang))
    restore = st.toggle(t("restore", lang), value=True, key="restore", help=t("restore_help", lang))

try:
    conn = connect(DB)  # not cached: Streamlit reruns the script in other threads, sqlite3 connections dislike that
except FileNotFoundError:
    st.error(f"No database found at `{DB}`.")
    st.stop()
with st.spinner(t("loading", lang)):
    agent = TravelAgent(conn, hotel_search(str(BROCHURES)), restore_activities=restore)
first_day, last_day = date_range(conn)
destinations = cities(conn)

# --------------------------------------------------------------------------------------------------------------
# The request. Inside a form, nothing runs until the search button is clicked.
# --------------------------------------------------------------------------------------------------------------
if st.session_state.get("wish", EXAMPLES[lang]) in EXAMPLES.values():
    st.session_state.wish = EXAMPLES[lang]  # an untouched example follows the language

with st.form("request"):
    left, middle, right = st.columns([2, 1, 2])
    # Stable keys: the labels change with the language, the values typed by the traveller must not. The city is
    # the exception: Streamlit would keep showing the selected name in the previous language, so this box is
    # rebuilt for each language and starts from the last city searched.
    last = st.session_state.get("last_request")
    start_city = last.city if last else "Madrid" if "Madrid" in destinations else destinations[0]
    city = left.selectbox(t("destination", lang), destinations, index=destinations.index(start_city),
                          key=f"city_{lang}", format_func=lambda key: city_name(key, lang))
    travellers = middle.number_input(t("travellers", lang), min_value=1, max_value=6, value=2, step=1,
                                     key="travellers")
    default_start = min(max(date(2026, 8, 12), first_day), last_day)
    # The return day may fall after the last flight in the database: only the departure needs one.
    stay = right.date_input(t("dates", lang), value=(default_start, default_start + timedelta(days=4)),
                            min_value=first_day, max_value=last_day + timedelta(days=30), format="DD/MM/YYYY",
                            help=t("dates_help", lang), key="stay")
    budget = st.number_input(t("budget", lang), min_value=150, max_value=5000, value=750, step=50, key="budget")
    wish = st.text_area(t("wish", lang), key="wish", height=100, help=t("wish_help", lang))
    submitted = st.form_submit_button(t("search", lang), type="primary", icon=":material/travel_explore:")

if submitted:
    if len(stay) != 2:
        st.info(t("pick_return", lang))
        st.stop()
    if (stay[1] - stay[0]).days < 1:
        st.warning(t("return_after", lang))
        st.stop()
    st.session_state.last_request = Request(city, stay[0].isoformat(), (stay[1] - stay[0]).days, int(travellers),
                                            float(budget), wish)
    st.session_state.confirming = False
    st.session_state.booking = None
    detected = detect_language(wish)
    if detected:
        st.session_state.detected = detected
        if choice == "auto" and detected != lang:
            st.rerun()  # redraw the whole page in the language of the wish

if "last_request" not in st.session_state:
    st.info(t("fill_form", lang))
    st.stop()

# The plan is kept between reruns: clicking the booking buttons must not recompute it (a booking takes seats,
# which could change the cheapest flight under the traveller's eyes). It is recomputed for a new request or setting.
request = st.session_state.last_request
if st.session_state.get("plan_key") != (request, restore):
    st.session_state.plan = agent.plan(request)
    st.session_state.plan_key = (request, restore)
plan = st.session_state.plan
trip = plan.trip

# --------------------------------------------------------------------------------------------------------------
# The result
# --------------------------------------------------------------------------------------------------------------
st.divider()
if trip is None:
    st.error(t("no_trip", lang, city=city_name(request.city, lang), budget=money(request.budget, lang)))
    if plan.notes:
        st.write(t("tried", lang))
        st.markdown("\n".join(f"- {line}" for line in log_lines(plan, lang)))
    st.info(t("hint_nothing", lang))
    st.stop()

flight, hotel = trip.flight, trip.hotel
end_day = (date.fromisoformat(trip.day) + timedelta(days=request.nights)).isoformat()
st.subheader(trip_title(trip, end_day, lang))

activities_price = sum(a["price"] for a in trip.activities)
gap = trip.total - request.budget
c1, c2, c3, c4 = st.columns(4)
c1.metric(t("flight", lang), money(flight["price"], lang),
          delta=f"{origin_name(flight['origin'], lang)} · {flight['departure_time']}", delta_color="off")
c2.metric(t("hotel", lang), money(hotel["price_per_night"] * request.nights, lang),
          delta=t("per_night", lang, price=money(hotel["price_per_night"], lang)), delta_color="off")
c3.metric(t("activities", lang), money(activities_price, lang),
          delta=count(len(trip.activities), "activity", lang), delta_color="off")
c4.metric(t("total", lang), money(trip.total, lang), delta_color="inverse",
          delta=t("vs_budget", lang, delta=("-" if gap < 0 else "+") + money(abs(gap), lang)))
st.caption(t("for_everyone", lang, total=money(trip.total_for_all, lang),
             travellers=count(request.travellers, "traveller", lang)))

if plan.notes:
    st.warning(t("log_title", lang) + "\n\n" + "\n".join(f"- {line}" for line in log_lines(plan, lang)))
else:
    st.success(t("all_fit", lang))

left, right = st.columns(2)
with left:
    st.subheader(hotel["hotel"])
    st.write("★" * int(hotel["stars"]) + f" · **{number(hotel['rating'], lang)}/10** "
             f"({count(int(hotel['reviews']), 'review', lang)}) · "
             + t("relevance", lang, score=number(hotel["score"], lang, 2)))
    st.caption(t("brochure", lang))
    st.write(hotel["text"])
with right:
    st.subheader(t("programme", lang))
    if trip.activities:
        for a in trip.activities:
            st.markdown(t("activity_line", lang, name=a["name"], category=category_name(a["category"], lang),
                          hours=number(a["hours"], lang), price=money(a["price"], lang)))
    else:
        st.markdown(t("no_activity", lang))
    st.subheader(t("your_flight", lang))
    st.markdown(t("flight_line", lang, flight=flight["flight"], origin=origin_name(flight["origin"], lang),
                  city=city_name(request.city, lang), day=day_label(trip.day, lang), time=flight["departure_time"],
                  hours=number(flight["hours"], lang)))

with st.expander(t("consulted", lang)):
    flights, hotels = agent.consulted(request)
    g, d = st.columns(2)
    g.markdown(t("flights_that_day", lang))
    g.dataframe(flights.drop(columns="id").head(15).rename(columns={
        "flight": t("col_flight", lang), "origin": t("col_origin", lang), "departure_time": t("col_time", lang),
        "hours": t("col_hours", lang), "price": t("col_price", lang), "seats_left": t("col_seats", lang)}),
        hide_index=True, width="stretch")
    d.markdown(t("closest_hotels", lang))
    d.dataframe(hotels[["hotel", "stars", "rating", "price_per_night", "score"]].rename(columns={
        "hotel": t("col_hotel", lang), "stars": t("col_stars", lang), "rating": t("col_rating", lang),
        "price_per_night": t("col_night", lang), "score": t("col_score", lang)}),
        hide_index=True, width="stretch")
    st.markdown(t("attempts", lang))
    st.dataframe(pd.DataFrame([{
        t("col_day", lang): day_label(a.day, lang), t("col_hotel", lang): a.hotel,
        t("col_flight", lang): a.flight_price, t("col_nights", lang): a.hotel_price,
        t("col_activities", lang): a.activities_price, t("col_total", lang): a.total,
        t("col_verdict", lang): verdict(a, lang)} for a in plan.attempts]), hide_index=True, width="stretch")

# --------------------------------------------------------------------------------------------------------------
# Booking, in two steps. The first click calls book() WITHOUT confirmation: nothing is written, the agent only says
# what it would do. The second click calls it again with confirm=True, and only then is the database changed.
# --------------------------------------------------------------------------------------------------------------
def ask_confirmation() -> None:
    st.session_state.confirming = True
    st.session_state.booking = None


def confirm_booking(trip, client: str) -> None:
    """Runs before the next rerun, so the page is drawn once the booking is done. Its own connection: a
    callback may run in another thread than the one that opened the page's connection."""
    connection = connect(DB)
    try:
        st.session_state.booking = book(connection, trip, client, confirm=True)
    finally:
        connection.close()
    st.session_state.confirming = False
    st.session_state.celebrate = st.session_state.booking.done


st.divider()
st.subheader(t("book_title", lang))
name_column, button_column = st.columns([3, 1], vertical_alignment="bottom")
client = name_column.text_input(t("name", lang), placeholder=t("name_placeholder", lang), key="client").strip()
button_column.button(t("book_button", lang), width="stretch", on_click=ask_confirmation)

if st.session_state.get("confirming"):
    if not client:
        st.warning(t("name_first", lang))
    else:
        st.info(booking_text(book(conn, trip, client), lang))  # confirm=False: nothing is written
        st.button(t("confirm_button", lang), type="primary", on_click=confirm_booking, args=(trip, client))

booking = st.session_state.get("booking")
if booking is not None:
    (st.success if booking.done else st.warning)(booking_text(booking, lang))
    if st.session_state.pop("celebrate", False):
        st.balloons()

st.caption(t("data_caption", lang))
