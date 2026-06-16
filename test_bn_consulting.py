"""
Teste automate pentru https://www.bn-consulting2016.com
Autor: generat pentru rulare in PyCharm cu pytest.

Instalare recomandata in terminalul PyCharm:
    python -m pip install pytest requests beautifulsoup4 selenium webdriver-manager

Rulare:
    pytest -v test_bn_consulting.py

Observatii:
- Testele de contact NU trimit formularul, doar verifica existenta campurilor.
- Testele cu Selenium pornesc Chrome in modul headless.
- Daca nu ai Chrome instalat, testele Selenium vor fi marcate ca skipped.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

import pytest
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.bn-consulting2016.com"
REQUEST_TIMEOUT = 15
MAX_RESPONSE_SECONDS = 10

PUBLIC_PAGES = {
    "home": "/",
    "despre_noi": "/despre-noi/",
    "echipa": "/echipa/",
    "contact": "/contact/",
    "zona_pentru_membri": "/zona-pentru-membri/",
}

EXPECTED_TEXT = {
    "/": [
        "Best Network Consulting",
        "Consultanta pentru administratie publica",
        "office@bn-consulting2016.com",
    ],
    "/despre-noi/": ["Despre noi", "SERVICII DE CONSULTANTA", "Portofoliu"],
    "/echipa/": ["Echipa", "Ungar Laura-Cristina", "Evaluator autorizat"],
    "/contact/": ["Contact", "BN Consulting SRL", "Va rugam sa ne contactati"],
    "/zona-pentru-membri/": ["membri", "cont", "pagini private"],
}

NAVIGATION_LABELS = [
    "Pagina de start",
    "Despre noi",
    "Echipa",
    "Contact",
    "Zona pentru membri",
]

CONTACT_LABELS = ["Nume", "E-mail", "Număr de telefon", "Data", "Cerinte"]
CONTACT_EMAILS = [
    "office@bn-consulting2016.com",
    "razvan.ungar@gmail.com",
    "bn.consulting2016@gmail.com",
]
CONTACT_PHONE_PATTERNS = [r"0774\s*903\s*493", r"0727\s*253\s*635", r"0750[\.\s]*27[\.\s]*29[\.\s]*62"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 AutomatedWebsiteTest/1.0"
)


@dataclass(frozen=True)
class PageResult:
    url: str
    status_code: int
    elapsed_seconds: float
    html: str
    soup: BeautifulSoup


@pytest.fixture(scope="session")
def http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_page(session: requests.Session, path_or_url: str) -> PageResult:
    url = path_or_url if path_or_url.startswith("http") else urljoin(BASE_URL, path_or_url)
    started = time.perf_counter()
    response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    elapsed = time.perf_counter() - started
    return PageResult(
        url=response.url,
        status_code=response.status_code,
        elapsed_seconds=elapsed,
        html=response.text,
        soup=BeautifulSoup(response.text, "html.parser"),
    )


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def visible_page_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return normalize_text(soup.get_text(" "))


def internal_links_from(html: str, current_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(current_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc.replace("www.", "") == urlparse(BASE_URL).netloc.replace("www.", ""):
            clean_url = parsed._replace(fragment="").geturl()
            links.add(clean_url)
    return links


def asset_urls_from(html: str, current_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for tag_name, attribute in [("img", "src"), ("script", "src"), ("link", "href")]:
        for tag in soup.find_all(tag_name):
            value = tag.get(attribute)
            if value:
                absolute = urljoin(current_url, value.strip())
                if absolute.startswith("http"):
                    urls.add(absolute)
    return urls


def assert_text_contains_all(page_text: str, expected_fragments: Iterable[str]) -> None:
    missing = [fragment for fragment in expected_fragments if normalize_text(fragment) not in page_text]
    assert not missing, f"Lipsesc din pagina urmatoarele texte asteptate: {missing}"


@pytest.mark.parametrize("page_name,path", PUBLIC_PAGES.items())
def test_public_pages_return_success_fast_and_html(http_session: requests.Session, page_name: str, path: str) -> None:
    page = fetch_page(http_session, path)

    assert page.status_code == 200, f"Pagina {page_name} nu raspunde cu HTTP 200"
    assert page.elapsed_seconds < MAX_RESPONSE_SECONDS, (
        f"Pagina {page_name} se incarca prea lent: {page.elapsed_seconds:.2f}s"
    )
    assert "text/html" in http_session.get(page.url, timeout=REQUEST_TIMEOUT).headers.get("Content-Type", "")
    assert len(page.html) > 1000, f"Pagina {page_name} pare goala sau incompleta"


@pytest.mark.parametrize("path,expected_fragments", EXPECTED_TEXT.items())
def test_public_pages_contain_expected_business_content(
    http_session: requests.Session, path: str, expected_fragments: list[str]
) -> None:
    page = fetch_page(http_session, path)
    assert_text_contains_all(visible_page_text(page.soup), expected_fragments)


def test_http_redirects_or_resolves_to_https(http_session: requests.Session) -> None:
    response = http_session.get("http://www.bn-consulting2016.com", timeout=REQUEST_TIMEOUT, allow_redirects=True)

    assert response.status_code == 200
    assert response.url.startswith("https://"), "Site-ul ar trebui sa ajunga pe HTTPS dupa redirect"


def test_main_navigation_links_are_present_on_homepage(http_session: requests.Session) -> None:
    page = fetch_page(http_session, "/")
    text = visible_page_text(page.soup)

    assert_text_contains_all(text, NAVIGATION_LABELS)


def test_contact_information_is_visible(http_session: requests.Session) -> None:
    page = fetch_page(http_session, "/contact/")
    text = visible_page_text(page.soup)

    for email in CONTACT_EMAILS:
        assert email.lower() in text, f"Adresa {email} nu este vizibila pe pagina de contact"

    missing_phones = [pattern for pattern in CONTACT_PHONE_PATTERNS if not re.search(pattern, text)]
    assert not missing_phones, f"Unele telefoane asteptate nu au fost gasite: {missing_phones}"


def test_contact_form_fields_exist_without_submitting(http_session: requests.Session) -> None:
    page = fetch_page(http_session, "/contact/")
    text = visible_page_text(page.soup)

    assert_text_contains_all(text, CONTACT_LABELS)
    assert "aplica" in text or "trimite" in text, "Nu am gasit butonul formularului de contact"

    forms = page.soup.find_all("form")
    assert forms, "Pagina de contact ar trebui sa contina cel putin un formular HTML"


def test_member_area_explains_private_access(http_session: requests.Session) -> None:
    page = fetch_page(http_session, "/zona-pentru-membri/")
    text = visible_page_text(page.soup)

    assert "membri" in text
    assert "cont" in text
    assert "pagini private" in text or "conținut" in text or "continut" in text


def test_each_public_page_has_basic_seo_elements(http_session: requests.Session) -> None:
    for path in PUBLIC_PAGES.values():
        page = fetch_page(http_session, path)
        title = page.soup.find("title")
        description = page.soup.find("meta", attrs={"name": "description"})
        headings = page.soup.find_all(["h1", "h2"])

        assert title and normalize_text(title.get_text()), f"Lipseste <title> pe {path}"
        assert len(normalize_text(title.get_text())) <= 70, f"Titlul SEO este prea lung pe {path}"
        assert headings, f"Pagina {path} nu are heading-uri H1/H2"

        # Meta description nu este obligatorie tehnic, dar este utila pentru SEO.
        # Daca pica, fie se adauga in CMS, fie se relaxeaza regula.
        assert description is not None, f"Lipseste meta description pe {path}"


def test_homepage_internal_links_are_not_broken(http_session: requests.Session) -> None:
    page = fetch_page(http_session, "/")
    links = internal_links_from(page.html, page.url)

    assert links, "Nu am gasit linkuri interne pe homepage"
    broken: list[str] = []
    for link in sorted(links):
        try:
            response = http_session.get(link, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if response.status_code >= 400:
                broken.append(f"{link} -> {response.status_code}")
        except requests.RequestException as exc:
            broken.append(f"{link} -> {exc.__class__.__name__}")

    assert not broken, "Linkuri interne defecte:\n" + "\n".join(broken)


def test_homepage_assets_are_reachable(http_session: requests.Session) -> None:
    page = fetch_page(http_session, "/")
    assets = asset_urls_from(page.html, page.url)

    assert assets, "Nu am gasit fisiere statice / imagini pe homepage"
    broken: list[str] = []
    for asset in sorted(assets)[:40]:  # limita ca testul sa ramana rapid
        try:
            response = http_session.get(asset, timeout=REQUEST_TIMEOUT, allow_redirects=True, stream=True)
            if response.status_code >= 400:
                broken.append(f"{asset} -> {response.status_code}")
        except requests.RequestException as exc:
            broken.append(f"{asset} -> {exc.__class__.__name__}")

    assert not broken, "Resurse statice defecte:\n" + "\n".join(broken)


def test_images_have_alt_text_on_public_pages(http_session: requests.Session) -> None:
    pages_with_missing_alt: dict[str, int] = {}

    for path in PUBLIC_PAGES.values():
        page = fetch_page(http_session, path)
        missing_alt = [img for img in page.soup.find_all("img") if not img.get("alt", "").strip()]
        if missing_alt:
            pages_with_missing_alt[path] = len(missing_alt)

    assert not pages_with_missing_alt, (
        "Exista imagini fara atribut alt. Recomandat pentru accesibilitate si SEO: "
        f"{pages_with_missing_alt}"
    )


@pytest.fixture(scope="session")
def driver():
    selenium = pytest.importorskip("selenium")
    pytest.importorskip("webdriver_manager")

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1366,900")

    try:
        browser = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as exc:  # pragma: no cover - depinde de mediul local
        pytest.skip(f"Chrome/Selenium nu este disponibil local: {exc}")

    browser.set_page_load_timeout(REQUEST_TIMEOUT)
    yield browser
    browser.quit()


def accept_cookie_banner_if_present(driver) -> None:
    from selenium.webdriver.common.by import By

    possible_texts = [
        "Acceptați doar ce e necesar",
        "Acceptați toate",
        "Acceptati doar ce e necesar",
        "Acceptati toate",
    ]
    for text in possible_texts:
        buttons = driver.find_elements(By.XPATH, f"//button[contains(normalize-space(), '{text}')]")
        if buttons:
            buttons[0].click()
            time.sleep(0.5)
            return


def test_homepage_renders_in_real_browser(driver) -> None:
    driver.get(BASE_URL)
    accept_cookie_banner_if_present(driver)

    assert "Best Network Consulting" in driver.page_source
    assert "Consultanta" in driver.page_source or "Consultanță" in driver.page_source


def test_navigation_works_in_real_browser(driver) -> None:
    from selenium.webdriver.common.by import By

    driver.get(BASE_URL)
    accept_cookie_banner_if_present(driver)

    for label in NAVIGATION_LABELS:
        assert driver.find_elements(By.PARTIAL_LINK_TEXT, label), f"Nu exista linkul de navigatie: {label}"


def test_contact_page_form_is_visible_in_real_browser(driver) -> None:
    from selenium.webdriver.common.by import By

    driver.get(urljoin(BASE_URL, "/contact/"))
    accept_cookie_banner_if_present(driver)
    body_text = driver.find_element(By.TAG_NAME, "body").text

    for label in CONTACT_LABELS:
        assert label in body_text, f"Campul/eticheta '{label}' nu este vizibil(a) in browser"

    # Nu dam click pe butonul Aplica/Trimite, pentru a evita trimiterea unei cereri reale.


@pytest.mark.parametrize(
    "width,height",
    [(390, 844), (768, 1024), (1366, 900)],
)
def test_homepage_is_responsive_at_common_viewports(driver, width: int, height: int) -> None:
    from selenium.webdriver.common.by import By

    driver.set_window_size(width, height)
    driver.get(BASE_URL)
    accept_cookie_banner_if_present(driver)
    body_text = driver.find_element(By.TAG_NAME, "body").text

    assert "Best Network Consulting" in body_text
    assert "Contact" in body_text
