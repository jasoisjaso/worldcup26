"""One-time seed script. Run with: python -m backend.db.seed"""
from datetime import datetime
from backend.db.session import init_db, SessionLocal
from backend.db.models import Team, Match


TEAMS = [
    ("mx", "Mexico", "MEX", "#006847"),
    ("za", "South Africa", "RSA", "#007A4D"),
    ("cz", "Czechia", "CZE", "#D7141A"),
    ("kr", "South Korea", "KOR", "#C60C30"),
    ("ca", "Canada", "CAN", "#FF0000"),
    ("ba", "Bosnia and Herzegovina", "BIH", "#002395"),
    ("qa", "Qatar", "QAT", "#8D1B3D"),
    ("ch", "Switzerland", "SUI", "#FF0000"),
    ("br", "Brazil", "BRA", "#009C3B"),
    ("ht", "Haiti", "HAI", "#00209F"),
    ("ma", "Morocco", "MAR", "#C1272D"),
    ("gb-sct", "Scotland", "SCO", "#003078"),
    ("us", "United States", "USA", "#002868"),
    ("py", "Paraguay", "PAR", "#D52B1E"),
    ("au", "Australia", "AUS", "#00843D"),
    ("tr", "Turkey", "TUR", "#E30A17"),
    ("de", "Germany", "GER", "#000000"),
    ("cw", "Curacao", "CUW", "#003DA5"),
    ("ci", "Ivory Coast", "CIV", "#F77F00"),
    ("ec", "Ecuador", "ECU", "#FFD100"),
    ("nl", "Netherlands", "NED", "#FF4F00"),
    ("jp", "Japan", "JPN", "#BC002D"),
    ("se", "Sweden", "SWE", "#006AA7"),
    ("tn", "Tunisia", "TUN", "#E70013"),
    ("be", "Belgium", "BEL", "#000000"),
    ("eg", "Egypt", "EGY", "#C8102E"),
    ("ir", "Iran", "IRN", "#239F40"),
    ("nz", "New Zealand", "NZL", "#00247D"),
    ("es", "Spain", "ESP", "#AA151B"),
    ("cv", "Cape Verde", "CPV", "#003893"),
    ("sa", "Saudi Arabia", "KSA", "#006C35"),
    ("uy", "Uruguay", "URU", "#5EB6E4"),
    ("fr", "France", "FRA", "#002395"),
    ("sn", "Senegal", "SEN", "#00853F"),
    ("iq", "Iraq", "IRQ", "#CE1126"),
    ("no", "Norway", "NOR", "#EF2B2D"),
    ("ar", "Argentina", "ARG", "#74ACDF"),
    ("dz", "Algeria", "ALG", "#006233"),
    ("at", "Austria", "AUT", "#ED2939"),
    ("jo", "Jordan", "JOR", "#007A3D"),
    ("pt", "Portugal", "POR", "#006600"),
    ("cd", "DR Congo", "COD", "#007FFF"),
    ("co", "Colombia", "COL", "#FCD116"),
    ("uz", "Uzbekistan", "UZB", "#1EB53A"),
    ("gb-eng", "England", "ENG", "#CF081F"),
    ("hr", "Croatia", "CRO", "#171796"),
    ("gh", "Ghana", "GHA", "#006B3F"),
    ("pa", "Panama", "PAN", "#DA121A"),
]


SEED_ELOS = {
    "ar": 2143, "br": 2083, "fr": 2072, "es": 2057, "pt": 2008, "de": 1989,
    "nl": 1981, "co": 1974, "be": 1934, "uy": 1932, "hr": 1916, "gb-eng": 1916,
    "mx": 1842, "ma": 1856, "ec": 1843, "us": 1798, "ch": 1850, "sn": 1841,
    "jp": 1832, "ir": 1792, "kr": 1772, "au": 1716, "ca": 1700, "tr": 1815,
    "sa": 1683, "cd": 1684, "dz": 1714, "py": 1722, "pa": 1631, "ci": 1730,
    "tn": 1700, "no": 1768, "at": 1798, "eg": 1738, "iq": 1623,
    "gb-sct": 1735, "cv": 1620, "uz": 1668, "se": 1790, "ht": 1500, "cw": 1530, "nz": 1571,
    "ba": 1697, "cz": 1748, "gh": 1659, "qa": 1666, "jo": 1648, "za": 1671,
}


# All 72 group-stage fixtures. Kickoffs in UTC (AEST - 10 hours).
# Source: FIFA official schedule via Soccergraph (verified June 2026).
MATCHES = [
    # -- Matchday 1 --
    ("M001", "A", 1, "2026-06-11T19:00:00", "Estadio Azteca, Mexico City",              "mx",     "za"),
    ("M002", "A", 1, "2026-06-12T02:00:00", "Estadio Akron, Guadalajara",               "kr",     "cz"),
    ("M003", "B", 1, "2026-06-12T19:00:00", "BMO Field, Toronto",                       "ca",     "ba"),
    ("M004", "D", 1, "2026-06-13T01:00:00", "SoFi Stadium, Los Angeles",                "us",     "py"),
    ("M005", "B", 1, "2026-06-13T19:00:00", "Levi Stadium, Santa Clara",                "qa",     "ch"),
    ("M006", "C", 1, "2026-06-13T22:00:00", "MetLife Stadium, New York",                "br",     "ma"),
    ("M007", "C", 1, "2026-06-14T01:00:00", "Gillette Stadium, Boston",                 "ht",     "gb-sct"),
    ("M008", "D", 1, "2026-06-14T04:00:00", "BC Place, Vancouver",                      "au",     "tr"),
    ("M009", "E", 1, "2026-06-14T17:00:00", "NRG Stadium, Houston",                     "de",     "cw"),
    ("M010", "F", 1, "2026-06-14T20:00:00", "AT&T Stadium, Dallas",                     "nl",     "jp"),
    ("M011", "E", 1, "2026-06-14T23:00:00", "Lincoln Financial Field, Philadelphia",    "ci",     "ec"),
    ("M012", "F", 1, "2026-06-15T02:00:00", "Estadio BBVA, Monterrey",                  "se",     "tn"),
    ("M013", "H", 1, "2026-06-15T16:00:00", "Mercedes-Benz Stadium, Atlanta",           "es",     "cv"),
    ("M014", "G", 1, "2026-06-15T19:00:00", "Lumen Field, Seattle",                     "be",     "eg"),
    ("M015", "H", 1, "2026-06-15T22:00:00", "Hard Rock Stadium, Miami",                 "sa",     "uy"),
    ("M016", "G", 1, "2026-06-16T01:00:00", "SoFi Stadium, Los Angeles",                "ir",     "nz"),
    ("M017", "I", 1, "2026-06-16T19:00:00", "MetLife Stadium, New York",                "fr",     "sn"),
    ("M018", "J", 1, "2026-06-17T01:00:00", "Arrowhead Stadium, Kansas City",           "ar",     "dz"),
    ("M019", "I", 1, "2026-06-16T22:00:00", "Gillette Stadium, Boston",                 "iq",     "no"),
    ("M020", "J", 1, "2026-06-17T04:00:00", "Levi Stadium, Santa Clara",                "at",     "jo"),
    ("M021", "K", 1, "2026-06-17T17:00:00", "NRG Stadium, Houston",                     "pt",     "cd"),
    ("M022", "L", 1, "2026-06-17T20:00:00", "AT&T Stadium, Dallas",                     "gb-eng", "hr"),
    ("M023", "K", 1, "2026-06-18T02:00:00", "Estadio Azteca, Mexico City",              "uz",     "co"),
    ("M024", "L", 1, "2026-06-17T23:00:00", "BMO Field, Toronto",                       "gh",     "pa"),

    # -- Matchday 2 --
    ("M025", "A", 2, "2026-06-18T16:00:00", "Mercedes-Benz Stadium, Atlanta",           "cz",     "za"),
    ("M026", "B", 2, "2026-06-18T19:00:00", "SoFi Stadium, Los Angeles",                "ch",     "ba"),
    ("M027", "B", 2, "2026-06-18T22:00:00", "BC Place, Vancouver",                      "ca",     "qa"),
    ("M028", "A", 2, "2026-06-19T01:00:00", "Estadio Akron, Guadalajara",               "mx",     "kr"),
    ("M029", "D", 2, "2026-06-19T19:00:00", "Lumen Field, Seattle",                     "us",     "au"),
    ("M030", "C", 2, "2026-06-19T22:00:00", "Gillette Stadium, Boston",                 "gb-sct", "ma"),
    ("M031", "C", 2, "2026-06-20T00:30:00", "Lincoln Financial Field, Philadelphia",    "br",     "ht"),
    ("M032", "D", 2, "2026-06-20T03:00:00", "Levi Stadium, Santa Clara",                "tr",     "py"),
    ("M033", "F", 2, "2026-06-20T17:00:00", "NRG Stadium, Houston",                     "nl",     "se"),
    ("M034", "E", 2, "2026-06-20T20:00:00", "BMO Field, Toronto",                       "de",     "ci"),
    ("M035", "E", 2, "2026-06-21T00:00:00", "Arrowhead Stadium, Kansas City",           "ec",     "cw"),
    ("M036", "F", 2, "2026-06-21T04:00:00", "Estadio BBVA, Monterrey",                  "tn",     "jp"),
    ("M037", "H", 2, "2026-06-21T16:00:00", "Mercedes-Benz Stadium, Atlanta",           "es",     "sa"),
    ("M038", "G", 2, "2026-06-21T19:00:00", "SoFi Stadium, Los Angeles",                "be",     "ir"),
    ("M039", "H", 2, "2026-06-21T22:00:00", "Hard Rock Stadium, Miami",                 "uy",     "cv"),
    ("M040", "G", 2, "2026-06-22T01:00:00", "BC Place, Vancouver",                      "nz",     "eg"),
    ("M041", "J", 2, "2026-06-22T17:00:00", "AT&T Stadium, Dallas",                     "ar",     "at"),
    ("M042", "I", 2, "2026-06-22T21:00:00", "Lincoln Financial Field, Philadelphia",    "fr",     "iq"),
    ("M043", "I", 2, "2026-06-23T00:00:00", "MetLife Stadium, New York",                "no",     "sn"),
    ("M044", "J", 2, "2026-06-23T03:00:00", "Levi Stadium, Santa Clara",                "jo",     "dz"),
    ("M045", "K", 2, "2026-06-23T17:00:00", "NRG Stadium, Houston",                     "pt",     "uz"),
    ("M046", "L", 2, "2026-06-23T20:00:00", "Gillette Stadium, Boston",                 "gb-eng", "gh"),
    ("M047", "L", 2, "2026-06-23T23:00:00", "BMO Field, Toronto",                       "pa",     "hr"),
    ("M048", "K", 2, "2026-06-24T02:00:00", "Estadio Akron, Guadalajara",               "co",     "cd"),

    # -- Matchday 3 (simultaneous within each group) --
    ("M049", "B", 3, "2026-06-24T19:00:00", "BC Place, Vancouver",                      "ch",     "ca"),
    ("M050", "B", 3, "2026-06-24T19:00:00", "Lumen Field, Seattle",                     "ba",     "qa"),
    ("M051", "C", 3, "2026-06-24T22:00:00", "Hard Rock Stadium, Miami",                 "gb-sct", "br"),
    ("M052", "C", 3, "2026-06-24T22:00:00", "Mercedes-Benz Stadium, Atlanta",           "ma",     "ht"),
    ("M053", "A", 3, "2026-06-25T01:00:00", "Estadio Azteca, Mexico City",              "cz",     "mx"),
    ("M054", "A", 3, "2026-06-25T01:00:00", "Estadio BBVA, Monterrey",                  "za",     "kr"),
    ("M055", "E", 3, "2026-06-25T20:00:00", "MetLife Stadium, New York",                "ec",     "de"),
    ("M056", "E", 3, "2026-06-25T20:00:00", "Lincoln Financial Field, Philadelphia",    "cw",     "ci"),
    ("M057", "F", 3, "2026-06-25T23:00:00", "AT&T Stadium, Dallas",                     "jp",     "se"),
    ("M058", "F", 3, "2026-06-25T23:00:00", "Arrowhead Stadium, Kansas City",           "tn",     "nl"),
    ("M059", "D", 3, "2026-06-26T02:00:00", "SoFi Stadium, Los Angeles",                "tr",     "us"),
    ("M060", "D", 3, "2026-06-26T02:00:00", "Levi Stadium, Santa Clara",                "py",     "au"),
    ("M061", "I", 3, "2026-06-26T19:00:00", "Gillette Stadium, Boston",                 "no",     "fr"),
    ("M062", "I", 3, "2026-06-26T19:00:00", "BMO Field, Toronto",                       "sn",     "iq"),
    ("M063", "H", 3, "2026-06-27T00:00:00", "Estadio Akron, Guadalajara",               "uy",     "es"),
    ("M064", "H", 3, "2026-06-27T00:00:00", "NRG Stadium, Houston",                     "cv",     "sa"),
    ("M065", "G", 3, "2026-06-27T03:00:00", "Lumen Field, Seattle",                     "eg",     "ir"),
    ("M066", "G", 3, "2026-06-27T03:00:00", "BC Place, Vancouver",                      "nz",     "be"),
    ("M067", "L", 3, "2026-06-27T21:00:00", "MetLife Stadium, New York",                "pa",     "gb-eng"),
    ("M068", "L", 3, "2026-06-27T21:00:00", "Lincoln Financial Field, Philadelphia",    "hr",     "gh"),
    ("M069", "K", 3, "2026-06-27T23:30:00", "Hard Rock Stadium, Miami",                 "co",     "pt"),
    ("M070", "K", 3, "2026-06-27T23:30:00", "Mercedes-Benz Stadium, Atlanta",           "cd",     "uz"),
    ("M071", "J", 3, "2026-06-28T02:00:00", "Arrowhead Stadium, Kansas City",           "dz",     "at"),
    ("M072", "J", 3, "2026-06-28T02:00:00", "AT&T Stadium, Dallas",                     "jo",     "ar"),
]


def seed():
    init_db()
    db = SessionLocal()
    try:
        for code, name, fifa_code, color in TEAMS:
            existing = db.get(Team, code)
            elo_seed = SEED_ELOS.get(code, 1500.0)
            if not existing:
                db.add(Team(
                    code=code,
                    name=name,
                    fifa_code=fifa_code,
                    primary_color=color,
                    flag_url=f"https://flagcdn.com/w80/{code}.png",
                    elo=elo_seed,
                ))
            else:
                if not existing.elo or existing.elo == 1500.0:
                    existing.elo = elo_seed

        for mid, group, matchday, kickoff_str, venue, home, away in MATCHES:
            existing = db.get(Match, mid)
            kickoff = datetime.fromisoformat(kickoff_str)
            if not existing:
                db.add(Match(
                    id=mid,
                    group=group,
                    matchday=matchday,
                    kickoff=kickoff,
                    venue=venue,
                    home_code=home,
                    away_code=away,
                ))
            else:
                existing.group = group
                existing.matchday = matchday
                existing.kickoff = kickoff
                existing.venue = venue
                existing.home_code = home
                existing.away_code = away

        db.commit()
        print(f"Seeded {len(TEAMS)} teams and {len(MATCHES)} matches")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
