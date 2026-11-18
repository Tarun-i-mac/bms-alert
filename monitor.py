import os, re, sys, requests
from playwright.sync_api import sync_playwright

CINEMA_URL = os.environ.get("BMS_URL") or "https://in.bookmyshow.com/cinemas/CHEN/rakki-cinemas-omr-kelambakkam/buytickets/RAKK/20261217"
KEYWORD = (os.environ.get("KEYWORD") or "doomsday").lower()
MOVIE_URL = os.environ.get("MOVIE_URL") or "https://in.bookmyshow.com/movies/chennai/avengers-doomsday/buytickets/ET00526306/20261217?etCodes=*&refEventCode=ET00526306"
MOVIE_KEYWORD = (os.environ.get("MOVIE_KEYWORD") or "rakki").lower()
TOKEN, CHAT = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
TITLE = re.compile(r"\((?:U|A|S|UA\s?\d*\+?)\)\s*$")


def notify(msg):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                  json={"chat_id": CHAT, "text": msg}, timeout=15).raise_for_status()


def load(ctx, url):
    page = ctx.new_page()
    resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(5000)
    for _ in range(8):  # cinema lists load lazily
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(700)
    status, final, text = (resp.status if resp else 0), page.url, page.inner_text("body")
    page.close()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    blocked = status >= 400 or "access denied" in text.lower() or len(text) < 200
    print(f"{url[:80]}... status={status} chars={len(text)} blocked={blocked}")
    return blocked, final, lines


def check_cinema(lines):
    """Primary: Rakki OMR page, look for the film's block."""
    segs, cur = [], None
    for l in lines:
        if TITLE.search(l):
            cur = [l]
            segs.append(cur)
        elif cur is not None:
            cur.append(l)
    hits = [s for s in segs if KEYWORD in s[0].lower()]
    if not hits:  # layout fallback
        for i, l in enumerate(lines):
            if KEYWORD in l.lower():
                hits = [lines[i:i + 12]]
                break
    return hits


def check_movie(lines):
    """Fallback: movie page across Chennai, look for Rakki."""
    for i, l in enumerate(lines):
        if MOVIE_KEYWORD in l.lower():
            return [lines[i:i + 10]]
    return []


results, blocked_all = [], True
with sync_playwright() as p:
    b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="en-IN", timezone_id="Asia/Kolkata")
    checks = [("Cinema page", CINEMA_URL, check_cinema),
              ("Movie page (fallback)", MOVIE_URL, check_movie)]
    for name, url, fn in checks:
        try:
            blocked, final, lines = load(ctx, url)
        except Exception as e:
            print(f"{name}: error {e}")
            continue
        if blocked:
            continue
        blocked_all = False
        hits = fn(lines)
        print(f"{name}: {'HIT' if hits else 'not yet'}")
        if hits:
            results.append((name, final, hits))
    b.close()

if results:
    msg = "🚨 Doomsday at Rakki OMR (Dec 17)"
    for name, final, hits in results:
        detail = "\n".join(" | ".join(h[:12]) for h in hits)
        msg += f"\n\n[{name}]\n{detail}\n{final}"
    notify(msg)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write("found=true\n")
    print("alerted")
elif blocked_all:
    print("All checks blocked or failed")
    sys.exit(2)
