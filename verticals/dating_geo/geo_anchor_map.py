"""
geo_anchor_map.py
=================
The single world-knowledge artifact the redesign needs. Given the live ad-group
inventory (the set of {ad_group_name: campaign} pulled by pull_scope), it produces an
anchor index that two consumers share:

  1. GUARD1's demonym map   (root cause #1 in the run report: 'chinese'/'haitian' missing)
  2. the geo-gate detector  (decides "is this term geo-bearing?" -> can Haiku negate it?)

It is committed to the repo as generated data and regenerated when the inventory changes.
The per-country DEMONYMS/CITIES below ARE the "one-time world-knowledge pass" the build
brief describes; in production they'd be emitted by an LLM pass over the inventory and
then frozen. Origin markets + homonyms come from the ACCOUNT BLOCK in classifier.md.

Token kinds the index distinguishes:
  target     - a partner-geo anchor (country name/demonym/city, region orphan demonym)
  general    - a campaign-general word (asian/european/slavic/latin...)
  subregion  - a sub-region word (scandinavian/balkan/caribbean...)
  origin     - the user's own seat (US/UK/CA/NZ/AU + their demonyms/cities) -> NOT routing
  ambiguous  - a homonym that could be origin OR target (odessa/georgia/panama...) -> escalate
  foreign    - a foreign-language dating signal (rencontre/citas/randki...) -> escalate
"""

# --------------------------------------------------------------------------------------
# WORLD-KNOWLEDGE LOOKUPS (the generated pass; demonym + key cities per country)
# Keyed by the ad-group NAME as it appears in the inventory (Filipina, not Philippines).
# --------------------------------------------------------------------------------------
COUNTRY_KNOWLEDGE = {
    # --- Asia-Search ---
    "China":       (["chinese"], ["beijing","shanghai","guangzhou","shenzhen","chengdu","hangzhou","wuhan","nanjing","xian","suzhou","tianjin","chongqing"]),
    "Japan":       (["japanese","gaijin"], ["tokyo","osaka","kyoto","yokohama","nagoya","sapporo","fukuoka","kobe","hiroshima","sendai","nara","okinawa"]),
    "Korea":       (["korean"], ["seoul","busan","incheon","daegu","daejeon","gwangju","jeju"]),
    "Thailand":    (["thai"], ["bangkok","phuket","pattaya","krabi","isaan","isan","chiang mai","chiangmai","koh samui","samui","hua hin"]),
    "Vietnam":     (["vietnamese","viet"], ["hanoi","saigon","danang","da nang","hoi an","nha trang"]),
    "India":       (["indian","desi"], ["mumbai","delhi","bangalore","bengaluru","kolkata","chennai","hyderabad","pune","jaipur","goa","ahmedabad"]),
    "Indonesia":   (["indonesian","balinese","bali"], ["jakarta","surabaya","bandung","yogyakarta","jogja","denpasar","ubud"]),
    "Filipina":    (["filipina","filipino","philippine","philippines","pinay","pinoy"], ["manila","cebu","davao","makati","quezon","taguig","pasig","iloilo"]),
    "Malaysia":    (["malaysian","malay"], ["penang","johor","melaka","malacca","langkawi","ipoh"]),  # 'kuala lumpur' multiword added below
    "Singapore":   (["singaporean"], ["singapore"]),
    "Cambodia":    (["cambodian","khmer"], ["phnom penh","siem reap"]),
    "Laos":        (["laotian","laos"], ["vientiane","luang prabang"]),
    "Kazakhstan":  (["kazakh","kazakhstan"], ["almaty","astana","nur sultan","nursultan","shymkent"]),
    "Kyrgyzstan":  (["kyrgyz","kyrgyzstan"], ["bishkek","osh"]),
    # --- Euro-Search ---
    "Germany":     (["german"], ["berlin","munich","hamburg","frankfurt","cologne","dusseldorf","düsseldorf","stuttgart","dortmund","leipzig"]),
    "France":      (["french"], ["paris","lyon","marseille","toulouse","bordeaux","lille","nantes","strasbourg","montpellier"]),  # 'nice' too risky (adjective)
    "Italy":       (["italian","italia"], ["rome","roma","milan","milano","naples","napoli","turin","torino","florence","firenze","venice","venezia","bologna","verona","palermo"]),
    "Spain":       (["spanish","spaniard","espana","españa"], ["madrid","barcelona","seville","sevilla","malaga","málaga","bilbao","valencia","alicante","granada","zaragoza"]),
    "Ireland":     (["irish"], ["dublin","cork","galway","limerick","waterford","tralee"]),
    "Denmark":     (["danish","dane"], ["copenhagen","kobenhavn","aarhus","odense","aalborg"]),
    "Sweden":      (["swedish","swede"], ["stockholm","gothenburg","goteborg","göteborg","malmo","malmö","uppsala"]),
    "Norway":      (["norwegian"], ["oslo","bergen","trondheim","stavanger","tromso","tromsø"]),
    "Finland":     (["finnish","finn"], ["helsinki","espoo","tampere","turku","oulu"]),
    "Switzerland": (["swiss"], ["zurich","zürich","geneva","geneve","genève","basel","bern","lausanne","lucerne"]),
    "Liechtenstein":(["liechtenstein"], ["vaduz"]),
    "Austria":     (["austrian"], ["vienna","wien","salzburg","graz","innsbruck","linz"]),
    "Belgium":     (["belgian"], ["brussels","bruxelles","brussel","antwerp","antwerpen","bruges","brugge","ghent","gent","liege","liège"]),
    "Greece":      (["greek","hellenic"], ["athens","athina","thessaloniki","salonika","patras","heraklion","crete","rhodes"]),
    "Iceland":     (["icelandic"], ["reykjavik","akureyri","keflavik"]),
    "Malta":       (["maltese","malta"], ["valletta"]),
    "Cyprus":      (["cypriot","cyprus"], ["nicosia"]),
    "Monaco":      (["monegasque","monaco"], ["monte carlo"]),
    "Portugal":    (["portuguese","portugal"], ["lisbon","lisboa","porto","oporto","algarve","braga","coimbra","faro","madeira"]),
    "Turkey":      (["turkish","turkey","turkiye","türkiye"], ["istanbul","ankara","izmir","antalya","bursa","bodrum","marmaris"]),
    # --- Slavic-Search ---
    "Russia":      (["russian"], ["moscow","moskva","novosibirsk","yekaterinburg","kazan"]),  # 'st petersburg' multiword below
    "Ukraine":     (["ukrainian","ukraine"], ["kyiv","kiev","odesa","lviv","kharkiv","dnipro","zaporizhzhia","vinnytsia"]),
    "Poland":      (["polish","pole"], ["warsaw","warszawa","krakow","kraków","wroclaw","wrocław","gdansk","gdańsk","poznan","poznán","lodz","łódź"]),
    "Bulgaria":    (["bulgarian"], ["plovdiv"]),       # 'sofia' withheld: collides w/ name-brand
    "Albania":     (["albanian"], ["tirana"]),
    "Armenia":     (["armenian","armenia"], ["yerevan"]),
    "Azerbaijan":  (["azerbaijani","azeri","azerbaijan"], ["baku"]),
    "Bosnia":      (["bosnian","bosnia","bosnia and herzegovina","herzegovina"], ["sarajevo","mostar","banja luka"]),
    "Croatia":     (["croatian","croatia"], ["zagreb","split","dubrovnik"]),
    "Czech":       (["czech","czechia","czech republic"], ["prague","praha","brno","ostrava"]),
    "Latvia":      (["latvian"], ["riga"]),
    "Lithuania":   (["lithuanian"], ["vilnius","kaunas"]),
    "Estonia":     (["estonian"], ["tallinn","tartu"]),
    "Georgia":     (["georgian"], ["tbilisi"]),        # NOTE: 'georgia' itself is a homonym (below)
    "Hungary":     (["hungarian"], ["budapest","debrecen","szeged"]),
    # --- Latin-Search ---
    "Brazil":      (["brazilian","brasil"], ["rio","salvador","brasilia","curitiba","fortaleza","recife","belo horizonte"]),  # 'sao paulo' multiword below
    "Mexico":      (["mexican","mexico"], ["guadalajara","cancun","tijuana","monterrey","puebla","merida","queretaro"]),
    "Colombia":    (["colombian"], ["bogota","medellin","cali","cartagena","barranquilla"]),
    "Cuba":        (["cuban"], ["havana"]),
    "Jamaica":     (["jamaican","jamaica"], ["kingston","montego bay"]),
    "Costa Rica":  (["costa rican","costarican","costa rica"], ["san jose"]),
    "Dominican Republic": (["dominican","dominicana","dominicano","dominican republic"], ["santo domingo","punta cana","santiago de los caballeros"]),
    "El Salvador": (["salvadoran","salvadorian","el salvador"], ["san salvador"]),
    "Guatemala":   (["guatemalan","guatemala"], ["guatemala city","antigua"]),
    "Honduras":    (["honduran","honduras"], ["tegucigalpa","san pedro sula"]),
    "Nicaragua":   (["nicaraguan","nicaragua"], ["managua","granada"]),
    "Peru":        (["peruvian","peru"], ["lima","cusco","cuzco","arequipa","trujillo"]),
    "Venezuela":   (["venezuelan","venezuela"], ["caracas","maracaibo","valencia","barquisimeto"]),
    "Bolivia":     (["bolivian"], []),
    "Belize":      (["belizean","belize"], []),
    "Haiti":       (["haitian","haiti"], []),
    "Puerto Rico": (["puerto rican","puertorican","puerto rico"], []),
    "Panama":      (["panamanian"], []),               # bare 'panama' is a homonym (below)
}

# Multiword cities (matched as substrings; safe because they contain a space/are distinctive)
MULTIWORD_CITIES = {
    "Malaysia": ["kuala lumpur"], "Russia": ["st petersburg","saint petersburg"],
    "Brazil": ["sao paulo"], "Mexico": ["mexico city"], "Filipina": ["quezon city"],
    "Vietnam": ["ho chi minh"], "Thailand": ["chiang mai","koh samui"],
}

# Region demonyms with NO own ad group -> ride to a sub-region / general (still target geo).
ORPHAN_TARGET_DEMONYMS = {
    # Asian orphans -> Eastern bucket
    "saudi","uzbek","afghan","mongolian","nepali","nepalese","bangladeshi","pakistani",
    "sri lankan","burmese","myanmar","taiwanese","tibetan","turkmen","tajik",
    # European orphans / Benelux / Balkan / Baltic members without own group
    "dutch","belgian","luxembourgish","austrian","greek","portuguese","icelandic",
    "estonian","serbian","croatian","bosnian","albanian","macedonian","montenegrin",
    "romanian","slovak","slovenian","czech","hungarian","moldovan",
    # Latin orphans -> Caribbean / Hispanic / Latina
    "argentine","argentinian","chilean","peruvian","venezuelan","ecuadorian","paraguayan",
    "uruguayan","guatemalan","honduran","nicaraguan","costa rican","salvadoran","dominican",
    "jamaican","trinidadian","bahamian","barbadian","aruban",
}

GENERAL_STEMS = {
    "Asia":   ["asian","asia"],
    "Europe": ["european","europe"],
    "Slavic": ["slavic","slav"],
    "Latina": ["latina","latino","latinas","latin"],
}
# Multiword general/region phrases (precedence handled downstream; here we only DETECT geo).
GENERAL_PHRASES = ["latin american","south american","central american","north american",
                   "eastern european","eastern europe",
                   # fused (no-space) variants seen in concatenated brand/query tokens
                   "latinamerican","southamerican","easterneuropean"]

# Foreign-language country names (a country named in its own/another language is still target).
FOREIGN_COUNTRY_NAMES = {"espana":"Spain","alemania":"Germany","japon":"Japan","japans":"Japan",
                         "italia":"Italy","italie":"Italy","allemagne":"Germany","ukraina":"Ukraine"}

# Country-code TLDs / language codes that show up as STANDALONE tokens (".de", "neu de").
# Curated: excludes English-word collisions (no/in/it/co/la/my/es/id/so/be->'be') and the
# ORIGIN ccTLDs (us/uk/ca/nz/au). Matched whole-token only (never fused) by the detector.
CCTLD = {
    "de": "Germany", "fr": "France", "nl": "Netherlands", "se": "Sweden", "dk": "Denmark",
    "fi": "Finland", "ch": "Switzerland", "ie": "Ireland", "pl": "Poland", "ru": "Russia",
    "ua": "Ukraine", "lt": "Lithuania", "lv": "Latvia", "bg": "Bulgaria", "ge": "Georgia",
    "br": "Brazil", "mx": "Mexico", "jp": "Japan", "kr": "Korea", "cn": "China",
    "th": "Thailand", "vn": "Vietnam", "ph": "Filipina", "sg": "Singapore",
    "kz": "Kazakhstan", "kg": "Kyrgyzstan",
    "pt": "Portugal", "at": "Austria", "gr": "Greece", "tr": "Turkey", "cz": "Czech",
    "hu": "Hungary", "hr": "Croatia",
    # orphan ccTLDs (no own group -> doctrine routes to sub-region/general)
    "ro": "_ORPHAN_", "rs": "_ORPHAN_",
}

# Well-known target-country regions/coasts that carry no demonym of their own. Seed set;
# grown from logs (the same way homonym_hints grows). Multiword entries match as substrings;
# single-word entries are distinctive enough to fuse-match safely.
REGIONS = {
    "costa del sol": "Spain", "costa brava": "Spain", "andalusia": "Spain",
    "andalucia": "Spain", "catalonia": "Spain", "tuscany": "Italy", "tuscan": "Italy",
    "sicily": "Italy", "sardinia": "Italy", "amalfi": "Italy", "provence": "France",
    "french riviera": "France", "bavaria": "Germany", "algarve": "_ORPHAN_",
}

SUBREGION_STEMS = {
    "Eastern":       ["oriental","eastern"],
    "Scandinavia":   ["scandinavian","scandinavia","nordic","viking"],
    "Mediterranean": ["mediterranean"],
    "Iberia":        ["iberian","iberia"],
    "Benelux":       ["benelux"],
    "Balkan":        ["balkans","balkan"],
    "Baltic":        ["baltic"],
    "Eastern Europe":["eastern european","eastern europe"],
    "Caribbean":     ["caribbean","carib"],
    "Hispanic":      ["hispanic"],
}

# --------------------------------------------------------------------------------------
# ORIGIN (the user's seat) — present alone => NOT geo-bearing (Haiku may mass-negate).
# --------------------------------------------------------------------------------------
ORIGIN_DEMONYMS = {"american","british","canadian","australian","aussie","kiwi","scottish",
                   "welsh","englishman"}
ORIGIN_COUNTRIES = {"usa","u.s.a","united states","u.s","uk","u.k","united kingdom","britain",
                    "great britain","canada","australia","new zealand","nz"}
ORIGIN_CITIES = {"new york","nyc","los angeles","chicago","houston","miami","dallas","boston",
                 "seattle","atlanta","phoenix","philadelphia","denver","austin","indiana",
                 "indianapolis","toronto","montreal","vancouver","ottawa","calgary","edmonton",
                 "sydney","melbourne","brisbane","adelaide","auckland","wellington",
                 "christchurch","manchester","liverpool","leeds","bristol","edinburgh",
                 "cardiff","belfast","nottingham","sheffield","perth"}

# --------------------------------------------------------------------------------------
# HOMONYMS — could be origin OR target. Always geo-bearing (=> escalate, never Haiku-negate)
# unless a same-term cue resolves it. From classifier.md homonym_hints + a few extras.
# --------------------------------------------------------------------------------------
HOMONYMS = {"odessa","georgia","valencia","cordoba","santiago","alexandria","birmingham",
            "london","panama","naples","florence","athens","ontario","cambridge",
            "richmond","columbia"}
# 'perth' (Australia / Scotland), both origin -> handled as origin, not ambiguous.
# Cues that resolve a homonym to ORIGIN (US/UK/CA/AU context in the same term).
ORIGIN_CUES = {"us","usa","u.s","tx","texas","fl","florida","ga","ca","ohio","va","virginia",
               "al","alabama","uk","ontario","canada","australia"}

# --------------------------------------------------------------------------------------
# FOREIGN-LANGUAGE dating signals -> geo-bearing (escalate; Sonnet applies LANG_KEEP).
# Specific dating/women/matchmaking words only; bare ultra-generic foreign words excluded.
# --------------------------------------------------------------------------------------
FOREIGN_DATING = {"rencontre","rencontres","citas","randki","partnervermittlung","frauen",
                  "kennenlernen","mujeres","chicas","donne","incontri","mulheres","namoro",
                  "knappenliebe","motesplatsen","singleboerse","singlebörse","asiatique",
                  "asiatica","asiatiques","femme","femmes"}

# Dating-context glue that legitimizes a FUSED anchor match (koreaDATES, ukraineCHARM...).
GLUE = {"dating","dates","date","dating","women","woman","girls","girl","ladies","brides",
        "bride","singles","single","cupid","charm","charms","hearts","heart","love","loves",
        "feels","vibe","vibes","talks","talk","match","matches","romance","mingle","meet",
        "kiss","beauty","beauties","wife","wives","lady","app","apps","com","net","site",
        "sites","online","near","reviews","review","people","peoplemeet","peoplemeets",
        "personals","connect","finder","seeking"}


def _expand_country_tokens(name):
    demos, cities = COUNTRY_KNOWLEDGE.get(name, ([], []))
    toks = {name.lower()} | set(d.lower() for d in demos) | set(c.lower() for c in cities)
    toks |= set(MULTIWORD_CITIES.get(name, []))
    toks |= {r for r, dest in REGIONS.items() if dest == name}        # named regions
    toks |= {t for t, dest in FOREIGN_COUNTRY_NAMES.items() if dest == name}
    return toks


def own_anchor_stems(ag):
    """The stems that anchor ad group `ag` to ITSELF (its own demonym/name/city, or its
    general/sub-region words). Used by the gate: a Haiku NEGATE of a term that contains the
    SERVED group's own anchor is the false-negate signature (china in China, dublin in
    Ireland, asian in Asia) and must escalate. A negate of a term that does NOT name its
    served group is either no-geo junk or a legit cross-negation -> safe for Haiku."""
    stems = set()
    if ag in COUNTRY_KNOWLEDGE:
        stems |= _expand_country_tokens(ag)
    if ag in GENERAL_STEMS:
        stems |= set(GENERAL_STEMS[ag])
    if ag in SUBREGION_STEMS:
        stems |= set(SUBREGION_STEMS[ag])
    return stems


def build_anchor_index(inventory):
    """
    inventory: dict {ad_group_name: campaign_name} (or any iterable of ad-group names).
    Returns an index of stem -> kind for the deterministic detector, plus the GUARD1
    demonym->country map (so the same artifact serves both consumers).
    """
    names = set(inventory.keys()) if isinstance(inventory, dict) else set(inventory)

    target_stems = {}       # stem -> destination (country/orphan)  [kind: target]
    general_stems = {}      # stem -> general
    subregion_stems = {}    # stem -> subregion
    demonym_to_country = {} # GUARD1 map: demonym/city/name -> own-country ad group

    # countries present as own ad groups
    for name in names:
        if name not in GENERAL_STEMS and name not in SUBREGION_STEMS:
            target_stems.setdefault(name.lower(), name)
            demonym_to_country.setdefault(name.lower(), name)
        if name in COUNTRY_KNOWLEDGE:
            for tok in _expand_country_tokens(name):
                target_stems[tok] = name
                demonym_to_country[tok] = name

    # orphan demonyms (no own group) — target, but route resolved later by doctrine
    for d in ORPHAN_TARGET_DEMONYMS:
        target_stems.setdefault(d, "_ORPHAN_")

    # foreign-language country names -> their own group if present, else orphan
    for tok, dest in FOREIGN_COUNTRY_NAMES.items():
        target_stems.setdefault(tok, dest if dest in names else "_ORPHAN_")

    # named regions -> their country if present, else orphan
    for tok, dest in REGIONS.items():
        target_stems.setdefault(tok, dest if dest in names else "_ORPHAN_")

    # ccTLDs: standalone-token geo signals. dest mapped to its group if present, else orphan.
    tld = {code: (dest if dest in names else "_ORPHAN_") for code, dest in CCTLD.items()}

    # generals / sub-regions actually present in the inventory
    for name in names:
        if name in GENERAL_STEMS:
            for s in GENERAL_STEMS[name]:
                general_stems[s] = name
        if name in SUBREGION_STEMS:
            for s in SUBREGION_STEMS[name]:
                subregion_stems[s] = name
    # general phrases always available if their general exists
    return {
        "target": target_stems,
        "general": general_stems,
        "subregion": subregion_stems,
        "general_phrases": GENERAL_PHRASES,
        "origin": ORIGIN_DEMONYMS | ORIGIN_COUNTRIES | ORIGIN_CITIES,
        "homonyms": HOMONYMS,
        "origin_cues": ORIGIN_CUES,
        "foreign": FOREIGN_DATING,
        "glue": GLUE,
        "tld": tld,                                  # <- standalone ccTLD signals
        "demonym_to_country": demonym_to_country,    # <- GUARD1 consumes this
    }
