#!/usr/bin/env python
#
# Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
# mailto:zooko@zooko.com
# See the end of this file for the free software, open source license (BSD-style).

# CVS:
__cvsid = '$Id: mtgspoiler.py,v 1.25 2003/01/23 01:04:52 zooko Exp $'

# HOWTO:
# 1. Get pyutil_new from `http://sf.net/projects/pyutil'.
# 2. Get mtgspoiler from `http://sf.net/projects/mtgspoiler'.
# 3. Get spoiler lists from `http://www.wizards.com/default.asp?x=magic/products/cardlists,,en'.
# 4. Make sure that your PYTHONPATH environment variable includes the pyutil_new
#    directory.
# 5. Change directories into the directory where you keep all the spoiler lists,
#    and run "mtgspoiler.py ./*".  (Thus instructing your bash shell to pass a
#    list of the names of the files in this directory to the incoming argument
#    list of mtgspoiler.py.)
# 6. Now you're in a Python interpreter with a local object named `d' containing the spoiler
#    database.  If you haven't already, learn Python from
#    `http://python.sourceforge.net/devel-docs/tut/tut.html'.  Assuming you are a hacker, this will
#    take only a couple of hours and can be enjoyably interlaced with the rest of these steps.
# 7. This Python command prints out all the cards in the database:
# d
# 8. This Python command assigns the (newly created) local variable `c' to
#    reference the first card in the database:
# c = d.cards()[0]
# 9. This one assigns `c' to reference the card named "Granite Grip".
# c = d['Granite Grip']
# 10. This Python command prints out this card:
# c
# 11. This Python command will tell you all the methods that you can invoke on `d':
# dir(d)
# 12. And this one tell you all the methods that you can invoke on `c':
# dir(c)
# 13. This one removes all cards have colored mana in their casting costs:
# d.filter_out_colors()
# 14. Now here is a cool and complicated one.  You'll have to read the inline docs for what it does.
# hosers = d.filter_in_useful_for_playing_colors("BU")
# 15. Okay, now please add features and submit patches.  Thanks!  --Zooko 2002-03-01


# TODO:
# * import "Oracle" errata and apply them...
# * merge double cards via number and not name (ap_spoiler doesn't have double-card names...)

# standard modules
import UserList, code, copy, exceptions, operator, re, string, sys, traceback, types, urllib

# pyutil modules (http://sf.net/projects/pyutil)
from pyutil import strutil
from pyutil import dictutil
from pyutil import humanreadable
from pyutil import randutil
from pyutil import VersionNumber

# Major, minor, micro (== bugfix release), nano (== not-publically-visible patchlevel), flag (== not-publically-visible UNSTABLE or STABLE flag)
versionobj = VersionNumber.VersionNumber(string.join(map(str, (0, 0, 7, 1,)), '.') + '-' + 'UNSTABLE')

true = 1
false = 0

RARITY_NAME_MAP = {
    'C': 'Common',
    'U': 'Uncommon',
    'R': 'Rare',
    'L': 'Land',
    }

COLOR_NAME_MAP = {
    'B': 'Black',
    'G': 'Green',
    'R': 'Red',
    'U': 'Blue',
    'W': 'White',
    }

COLOR_BASICLAND_MAP = {
    'B': 'Swamp',
    'G': 'Forest',
    'R': 'Mountain',
    'U': 'Island',
    'W': 'Plains',
    }

SET_NAME_ABBREV_MAP = { # incomplete
    'Torment': 'TR',
    'Onslaught': 'ON',
    'Seventh Edition': '7E',
    'Odyssey': 'OD',
    'Judgment': 'JU',
    'Invasion': 'IN',
    'Planeshift': 'PL',
    'Apocalypse': 'AP',
    'Homelands': 'HL',
    "Urza's Legacy": 'UL',
    "Mirage": 'MR',
    "Tempest": 'TP',
    "Urza's Saga": 'US',
    "Alpha/Beta/Unlimited": 'UN',
    "Revised": 'RV',
    "Judgment": 'JU',
    "Disrupt": 'WL',
    "Nemesis": 'NE',
    "Alliances": 'AL',
    "Mercadian Masques": 'MM',
    "Prophecy": 'PR',
    "Seventh Edition": '7E',
    "Arabian Nights": 'AN',
    }

def findmagiccards_url(c):
    """
    e.g.
    http://www.findmagiccards.com/Cards/to/Nantuko_Blightcutter.html
    """
    return "http://www.findmagiccards.com/Cards/" + SET_NAME_ABBREV_MAP[c['Set Name']] + "/" + c['Card Name'].replace(" ", "_").replace(",", "_").replace("'", "_") + ".html"

def findmagiccards_page(c):
    return urllib.urlopen(findmagiccards_url(c)).read()

FMC_PRICE_RE=re.compile("Price :</TD><TD>\$ *([0-9]*.[0-9][0-9])", re.IGNORECASE)
def findmagiccards_price(c):
    page = None
    mo = None
    try:
        page = findmagiccards_page(c)
        mo = FMC_PRICE_RE.search(page)
        if mo is None:
            return None
        return mo.group(1)
    except exceptions.StandardError, le:
        raise exceptions.StandardError, { 'cause': le, 'page': page, 'mo': mo, 'mo.group(0)': (mo is not None) and mo.group(0), }
   
def cmppow(x, y):
    if x.get('Pow') and y.get('Pow'):
        return cmp(x['Pow'], y['Pow'])
    else:
        return cmp(x, y)
     
def cmpDOLLARPRICE(x, y):
    if x['DOLLARPRICE'] and y['DOLLARPRICE']:
        return cmp(float(x['DOLLARPRICE']), float(y['DOLLARPRICE']))
    else:
        return cmp(x['DOLLARPRICE'], y['DOLLARPRICE'])

def cmpmanacost(x, y):
    res = cmp(x.converted_mana_cost(), y.converted_mana_cost())
    if res != 0:
        return res
    res = cmp(len(x.colored_mana_cost()), len(y.colored_mana_cost()))
    if res != 0:
        return res
    # Heh.  This part is a value judgement, but without it, it would be a tie.  --Zooko 2002-03-03
    # XXX We could search in Card Text for "as an added cost" or whatever...  --Zooko 2002-03-03
    colorscarcity={
        "G": 1,
        "W": 2,
        "B": 3,
        "R": 4,
        "U": 5,
        }
    xc = 0
    for c in x.colored_mana_cost():
        xc += colorscarcity[c]
    yc = 0
    for c in y.colored_mana_cost():
        yc += colorscarcity[c]
    res = cmp(xc, yc)
    if res != 0:
        return res
    # Oh well, just for prettiness when looking at listings, let's sort by name.
    return cmp(x["Card Name"], y["Card Name"])

UPDATE_NAMES={
    "Card Title": "Card Name",
    "Pow/Tough": "Pow/Tou",
    "Pow/Tgh": "Pow/Tou",
    "Casting Cost": "Mana Cost",
    "Cost": "Mana Cost",
    "Card Type": "Type & Class",
    "Card Rarity": "Rarity",
    "CardCard Type": "Type & Class",
    "Type": "Type & Class",
    "Color": "Card Color",
    "Artists": "Artist",
    "Illus": "Artist",
    }

RARITY_RE=re.compile("(Dirt Common|Common|Uncommon|Rare|Land|C|U|R|L) ?([1-9][0-9]*(/[1-9][0-9]*(/[1-9][0-9]*)?)?)?$")
UPDATE_RARITIES={
    'Dirt Common': 'L', # XXX Not sure if revised.txt's "Dirt Common 1" is the same as L.
    'Common': 'C',
    'Uncommon': 'U',
    'Rare': 'R',
    'Land': 'L',
    'C': 'C',
    'U': 'U',
    'R': 'R',
    'L': 'L',
    }

def _fixnames(name):
    name = name.replace('\xc6', 'AE')
    # alliances.txt, arabian_nights.txt, and homelands.txt have "(2 versions)" in the Card Name.
    mo = CARDNAME_K_VERSIONS_RE.match(name)
    if mo:
        name = mo.group(1)
    return name

class Card(dictutil.UtilDict):
    def __init__(self, initialdata={}):
        dictutil.UtilDict.__init__(self, initialdata)

    def __repr__(self):
        return self.pretty_print()

    def __str__(self):
        return self.pretty_print()

    def _update(self):
        """
        Make sure this card instance uses all new terminology.
        """
        for old, new in UPDATE_NAMES.items():
            if self.has_key(old):
                self[new] = self[old]
                del self[old]
        assert self.has_key('Rarity'), "self.data: %s" % `self.data`
        mo = RARITY_RE.match(self['Rarity'])
        assert mo is not None, { 'Rarity': self['Rarity'], 'self': self, }
        self['Rarity'] = UPDATE_RARITIES[mo.group(1)] + (mo.group(2) or "")

        # Different spoiler lists do different things for the "Mana Cost" of a land.  What *we* do is remove it from the dict entirely.
        # (When exporting a spoiler list, it will be printed as "n/a", which is how the new spoiler lists do it.)
        try:
            if LAND_TYPE_AND_CLASS_RE.search(self["Type & Class"]):
                self.del_if_present("Mana Cost")
        except exceptions.StandardError, le:
            print humanreadable.hr(le)
            print humanreadable.hr(self)
            raise exceptions.StandardError, { 'cause': le, 'self': self }

        # If it doesn't have a 'Card Color', and it is an artifact, then make its 'Card Color' be "Artifact", which is what newer spoiler lists do.
        if not self.has_key('Card Color') and self.is_artifact():
            self['Card Color'] = "Artifact"

    def fetch_latest_price(self):
        self['DOLLARPRICE'] = findmagiccards_price(self)

    def copy(self):
        res = Card()
        for k, v in self.items():
            res[k] = v
        return res

    def converted_mana_cost(self):
        cc = 0
        num = "0"
        mc = self.get("Mana Cost", '0')
        if mc.find("/") != -1:
            mc = mc[:mc.find("/")] # for double-cards.
        for char in mc:
            if char in "BGRUW":
                cc+=1
            elif char in "X":
                # whatever...
                pass
            else:
                num += char
        cc += int(num)
        return cc

    def colored_mana_cost(self):
        mc = self.get("Mana Cost", '0')
        if mc.find("/") != -1:
            mc = mc[:mc.find("/")] # ??? for double-cards.
        return filter(lambda c: c in "BGRUW", mc)

    def colors(self):
        cs = []
        for c in self.colored_mana_cost():
            if not c in cs:
                cs.append(c)
        return string.join(cs, '')

    def is_creature(self):
        return CREATURE_TYPE_AND_CLASS_RE.search(self["Type & Class"])

    def is_land(self):
        return LAND_TYPE_AND_CLASS_RE.search(self["Type & Class"])

    def is_enchantment(self):
        return ENCHANTMENT_TYPE_AND_CLASS_RE.search(self["Type & Class"])

    def is_artifact(self):
        return ARTIFACT_TYPE_AND_CLASS_RE.search(self["Type & Class"])

    def is_permanent(self):
        return self.is_land() or self.is_artifact() or self.is_creature() or self.is_enchantment()

    def is_instant(self):
        return INSTANT_TYPE_AND_CLASS_RE.search(self["Type & Class"]) or INSTANT_CARD_TEXT_RE.search(self["Card Text"])
        
    def full_print(self):
        """
        @returns a string containing the full "spoiler" form
        """
        s = ""
        def formfield(s, k, v):
            # XXX this is incredibly inefficient...  --Zooko 2002-03-04
            s+=k+':'
            if len(k) < 7:
                s+='\t'
            s+='\t'
            if v is not None:
                s+=v
            s+='\n'
            return s

        ks = self.keys()
        for k in ("Card Name", "Card Color",):
            if self.has_key(k):
                s = formfield(s, k, self[k])
                ks.remove(k)
        s = formfield(s, "Mana Cost", self.get("Mana Cost", "n/a"))
        if "Mana Cost" in ks:
            ks.remove("Mana Cost")
        for k in ("Type & Class", "Pow/Tou", "Card Text", "Flavor Text", "Artist", "Rarity"):
            if self.has_key(k):
                s = formfield(s, k, self[k])
                ks.remove(k)

        if "Pow" in ks:
            ks.remove("Pow")
        if "Tou" in ks:
            ks.remove("Tou")

        if "Card #" in ks:
            ks.remove("Card #")

        for k in copy.copy(ks):
            s = formfield(s, k, self[k])
            ks.remove(k)

        if self.has_key('Card #'):
            s = formfield(s, "Card #", self["Card #"])
        s+="\n"
        return s

    def terse_print(self):
        """
        @returns a string containing the terse form
        """
        res = ""
        if self.get("Mana Cost") is not None:
            res += self["Mana Cost"] + ": "
        res += self["Card Name"]
        if self.get("Pow/Tou") is not None:
            res += " " + self["Pow/Tou"]
        return res

    def pretty_print(self, includeartist=false, includeflavortext=false, includecardcolor=false, includecardnumber=false):
        """
        @returns a string containing the pretty form
        """
        ks = self.keys()
        if 'DOLLARPRICE' in ks:
            ks.remove('DOLLARPRICE')
        res = self['Card Name'] + '\n'
        ks.remove('Card Name')
        if self.has_key('Mana Cost'):
            res += self['Mana Cost'] + ', '
            ks.remove('Mana Cost')
        res += self['Type & Class']
        ks.remove('Type & Class')
        if self.get('Pow/Tou'):
            res += ' ' + self['Pow/Tou']
        if 'Pow/Tou' in ks:
            ks.remove('Pow/Tou')
        if 'Pow' in ks:
            ks.remove('Pow')
        if 'Tou' in ks:
            ks.remove('Tou')
        if self.get('Set Name'):
            res += ', '
            res += self['Set Name']
            ks.remove('Set Name')
        if len(self['Rarity']) > 1:
            res += ' ' + RARITY_NAME_MAP[self['Rarity'][0]] + ' ' + self['Rarity'][1:] + '\n'
        else:
            res += ' ' + RARITY_NAME_MAP[self['Rarity']] + '\n'
        ks.remove('Rarity')
        # assert self.has_key('Card Text'), { 'self': self, 'self.data': self.data, } # This is just for debugging.  It's okay if a card doesn't have card text.
        if self.get('Card Text'):
            res += self['Card Text'] + '\n'
        if 'Card Text' in ks:
            ks.remove('Card Text')
        if includeflavortext and self.get('Flavor Text'):
            res += self['Flavor Text'] + '\n'
        if 'Flavor Text' in ks:
            ks.remove('Flavor Text')
        # assert self.has_key('Artist'), { 'self': self, 'self.data': self.data, } # This is just for debugging.  It's okay if a card doesn't have Artist.
        if includeartist and self.get('Artist'):
            res += self['Artist'] + '\n'
        if 'Artist' in ks:
            ks.remove('Artist')
        if includecardcolor and self.get('Card Color'):
            res += self['Card Color'] + '\n'
        try:
            ks.remove('Card Color')
        except exceptions.StandardError, le:
            raise exceptions.StandardError, { 'problem': 'Card Color not found.', 'cause': le, 'self': self, }
        
        if includecardnumber:
            res += self['Card #'] + '\n'
        if 'Card #' in ks:
            ks.remove('Card #')

        for k in ks:
            if self[k]:
                res += k + ': ' + self[k] + '\n'

        return res

CARDS_TOTAL_RE=re.compile("([1-9][0-9]*) Cards? Total", re.IGNORECASE)
SPOILER_NAME_RE=re.compile("(.*?) (Spoiler|Spoiler List|Card Spoiler List|Edition Card List|Card List)$", re.IGNORECASE)

CARDNAME_K_VERSIONS_RE_STR="(.*?)( (\(([2-9][0-9]*) ?versions\)))?\s*$"
CARDNAME_K_VERSIONS_RE=re.compile(CARDNAME_K_VERSIONS_RE_STR, re.IGNORECASE)
CARDNAME_FIELD_RE=re.compile("Card (Name|Title):\s*" + CARDNAME_K_VERSIONS_RE_STR)

DOUBLE_CARD_NAME_RE=re.compile("(.*)/(.*) \((.*)\)")
LAND_TYPE_AND_CLASS_RE=re.compile("(?<![Ee]nchant )[Ll]and")
CREATURE_TYPE_AND_CLASS_RE=re.compile("(?<![Ee]nchant )[Cc]reature|Summon ")
ENCHANTMENT_TYPE_AND_CLASS_RE=re.compile("[Ee]nchant")
ARTIFACT_TYPE_AND_CLASS_RE=re.compile("(?<![Ee]nchant )[Aa]rtifact")
INSTANT_TYPE_AND_CLASS_RE=re.compile("[Ii]nstant|[Ii]nterrupt")
INSTANT_CARD_TEXT_RE=re.compile("[Yy]ou may play .* any time you could play an instant")

UL_CARDNAME_RE_STR="(.*?)\s*"
UL_MANACOST_RE_STR="([X1-9]*[BGRUW]*)\s*" # opt
UL_TYPECLASS_RE_STR="(.*?)\s*"
UL_RARITY_RE_STR="([RUC])\s*"
UL_POWTUF_RE_STR="([0-9]*\**X*/[0-9]*\**X*)\s*" # opt
UL_CARDTEXT_RE_STR="(.*?)\s*"
UL_ARTIST_RE_STR="Illus. (.*?)\s*"
UL_CARDNUM_RE_STR="([0-9]*)/([0-9]*)\s*"

URZAS_LEGACY_CARD_RE=re.compile("^" + UL_CARDNAME_RE_STR + "\n" + "(?:" + UL_MANACOST_RE_STR + "\n)?" + UL_TYPECLASS_RE_STR + "\n" + UL_RARITY_RE_STR + "\n" + "(?:" + UL_POWTUF_RE_STR + "\n)?" + UL_CARDTEXT_RE_STR + "\n" + UL_ARTIST_RE_STR + "\n" + UL_CARDNUM_RE_STR, re.MULTILINE + re.DOTALL)

SQUOTED_RE=re.compile("^'(.*)'$")
DQUOTED_RE=re.compile('^"(.*)"$')

def strip_whitespace_and_quotes(l):
    """
    @returns: l, minus any leading and trailing combination of whitespace and
        matched pairs of quotation characters: "'" or '"'
    """
    oldl = None
    while oldl != l:
        oldl = l
        l = l.strip()
        mo = SQUOTED_RE.match(l)
        if mo:
            l = mo.group(1)
        mo = DQUOTED_RE.match(l)
        if mo:
            l = mo.group(1)
    return l

class DB(dictutil.UtilDict):
    def __init__(self, initialdata={}, importfile=None):
        # k: cardname, v: {}
        dictutil.UtilDict.__init__(self, initialdata)
        if importfile is not None:
            self.import_list(importfile)

    def fetch_latest_prices(self):
        for c in self.cards():
            assert isinstance(c, Card)
            c.fetch_latest_price()

    def copy(self):
        res = DB()
        for k, v in self.items():
            res[k] = v.copy()
        return res

    def terse_print(self):
        l = self.cards()
        l.sort(cmpmanacost)
        for c in l:
            print c.terse_print()

    def __repr__(self):
        return string.join(map(lambda x: x + '\n', map(Card.pretty_print, self.cards())))

    def __str__(self):
        return string.join(map(Card.pretty_print, self.cards()))

    def filter_in(self, keyre, valre):
        if type(keyre) is types.StringType:
            keyre = re.compile(keyre)
        if type(valre) is types.StringType:
            valre = re.compile(valre)
        for cardname, card in self.items():
            match = false
            for key, val in card.items():
                if keyre.search(key) and valre.search(str(val)):
                    match = true
                    break
            if not match:
                del self[cardname]

    def filter_out(self, keyre, valre):
        if type(keyre) is types.StringType:
            keyre = re.compile(keyre)
        if type(valre) is types.StringType:
            valre = re.compile(valre)
        for cardname, card in self.items():
            for key, val in card.items():
                if keyre.search(key) and valre.search(str(val)):
                    del self[cardname]
                    break

    def filter(self, keyre, valre, filterin=false):
        """
        @param keyre regex applied to key
        @param valre regex applied to val
        @param filterin `true' iff items that match are kept (filtered "in") instead of removed (filtered out)
        """
        if filterin:
            return self.filter_in(keyre, valre)
        else:
            return self.filter_out(keyre, valre)

    def filter_out_colors(self, colors='RGWUB'):
        for name, card in self.items():
            if len(filter(lambda color, card=card: color in card.get('Mana Cost', ''), colors)) > 0:
                del self[name]

    def filter_in_colors(self, colors='RGWUB'):
        for name, card in self.items():
            if len(filter(lambda color, card=card: color in card.get('Mana Cost', ''), colors)) == 0:
                del self[name]

    def filter_out_uses_or_generates_mana(self, mana="BGRUW"):
        # The `o?' part is because of some kind of typo in in_spoiler_en_alpha.txt.
        self.filter_out("Card Text", "(^|[^A-Za-z])[BGRUW0-9X]*o?[" + mana + "][BGRUW0-9X]*[^A-Za-z]")

    def filter_in_uses_or_generates_mana(self, mana="BGRUW"):
        self.filter_in("Card Text", "(^|[^A-Za-z])[BGRUW0-9X]*o?[" + mana + "][BGRUW0-9X]*[^A-Za-z]")

    def filter_out_affects_color_or_basic_land(self, colors="BGRUW"):
        """
        Removes all cards which mention colors by name (i.e. "white", not "W" nor "[W]", which both denote mana) or the associated basic land (i.e. "Plains").
        """
        r = "([^A-Z]|^)((non)?" + COLOR_NAME_MAP[colors[0]] + "|" + COLOR_BASICLAND_MAP[colors[0]] + "s?"
        for color in colors[1:]:
            r += "|" + COLOR_NAME_MAP[color] + "|" + COLOR_BASICLAND_MAP[color] + "s?"
        r += ")([^A-Z]|$)"
        ro = re.compile(r, re.IGNORECASE)

        self.filter_out("Card Text", ro)

    def filter_in_affects_color(self, colors="BGRUW"):
        """
        Removes all cards which do not mention colors by name (i.e. "white", not "W" nor "[W]", which both denote mana).
        """
        r = "([^A-Z]|^)((non)?" + COLOR_NAME_MAP[colors[0]]
        for color in colors[1:]:
            r += "|" + COLOR_NAME_MAP[color]
        r += ")([^A-Z]|$)"
        ro = re.compile(r, re.IGNORECASE)

        self.filter_in("Card Text", ro)

    def filter_in_affects_color_or_basic_land(self, colors="BGRUW"):
        """
        Removes all cards which do not mention either colors by name (i.e. "white", not "W" nor "[W]", which both denote mana) or the associated basic land (i.e. "Plains").
        """
        r = "([^A-Z]|^)((non)?" + COLOR_NAME_MAP[colors[0]] + "|" + COLOR_BASICLAND_MAP[colors[0]] + "s?"
        for color in colors[1:]:
            r += "|" + COLOR_NAME_MAP[color] + "|" + COLOR_BASICLAND_MAP[color] + "s?"
        r += ")([^A-Z]|$)"
        ro = re.compile(r, re.IGNORECASE)

        self.filter_in("Card Text", ro)

    def filter_in_landwalk(self, colors="BGRUW"):
        r = "([^A-Z]|^)(" + COLOR_BASICLAND_MAP[colors[0]] + "walk"
        for color in colors[1:]:
            r += "|" + COLOR_BASICLAND_MAP[color] + "walk"
        r += ")([^A-Z]|$)"
        ro = re.compile(r, re.IGNORECASE)

        self.filter_in("Card Text", ro)

    def filter_out_landwalk(self, colors="BGRUW"):
        r = "([^A-Z]|^)(" + COLOR_BASICLAND_MAP[colors[0]] + "walk"
        for color in colors[1:]:
            r += "|" + COLOR_BASICLAND_MAP[color] + "walk"
        r += ")([^A-Z]|$)"
        ro = re.compile(r, re.IGNORECASE)

        self.filter_out("Card Text", ro)

    def filter_in_useful_for_playing_colors(self, colors):
        """
        Removes all cards which aren't "useful" for playing a deck that uses only `colors':

        1. Remove all cards which use or provide mana of an excluded color.
        2. Remove all cards which affect cards of an excluded color.
        3. Remove all cards with landwalk.

        It also returns a DB instance containing all of the cards which are filtered out *only* because they affect cards of an excluded color or because they have landwalk (some of these are actually still useful even though you can't use all of their abilities, and others (like the landwalks) are "color hosers" which are useful against certain other colors).
        """
        hosers = DB()
        othercolors = ""
        for color in "BGRUW":
            if not color in colors:
                othercolors += color
        self.filter_out_colors(othercolors) # remove all cards whose casting cost involves excluded colors
        self.filter_out_uses_or_generates_mana(othercolors) # remove all cards which use or generate mana of excluded colors
        affectors = self.copy()
        self.filter_out_affects_color_or_basic_land(othercolors) # remove all cards which affect excluded colors
        affectors.filter_in_affects_color_or_basic_land(othercolors) # filter in cards which affect excluded colors
        landwalks = self.copy()
        landwalks.filter_in_landwalk()
        self.filter_out_landwalk() # remove all cards which involve landwalk
        hosers.update(affectors)
        hosers.update(landwalks)
        return hosers

    def filter_out_rarities(self, rarities="R"):
        for name, card in self.items():
            if card['Rarity'] in rarities:
                del self[name]

    def filter_in_rarities(self, rarities="R"):
        for name, card in self.items():
            if not card['Rarity'] in rarities:
                del self[name]

    def cards(self):
        return self.values()

    def _process_key_and_val(self, thiskey, thisval, thiscard):
        thisval = strip_whitespace_and_quotes(thisval)
        thiskey = UPDATE_NAMES.get(thiskey, thiskey)
        if thiskey == "Card Name":
            thisval = _fixnames(thisval)
            self.data[thisval] = thiscard
        elif thiskey == "Pow/Tou":
            if thisval.lower() == "n/a":
                thisval = ""
            if thisval.find('/') != -1:
                try:
                    thiscard['Pow'] = int(thisval[:thisval.find('/')])
                except ValueError:
                    # Oh, this must be a "special" Pow.
                    thiscard['Pow'] = thisval[:thisval.find('/')]
                try:
                    thiscard['Tou'] = int(thisval[thisval.find('/')+1:])
                except ValueError:
                    # Oh, this must be a "special" Tou.
                    thiscard['Tou'] = thisval[thisval.find('/')+1:]

        if thiskey:
            thiscard[thiskey] = thisval
            # assert not ((thiskey == "Mana Cost") and (strip_whitespace_and_quotes(thisval).find("and") != -1)), "thiscard.data: %s, thiskey: %s, thisval: %s" % (thiscard.data, thiskey, thisval,) # we fix this in "_update()".
        
    def _find_missing_names(self, fname):
        f = open(fname, 'r')
        names = dictutil.NumDict()
        for line in f.xreadlines():
            mo = CARDNAME_FIELD_RE.match(strutil.pop_trailing_newlines(line))
            if mo:
                if mo.group(5):
                    names.add_num(_fixnames(mo.group(2)), int(mo.group(5)))
                else:
                    names.inc(_fixnames(mo.group(2)))

        for k, v, in names.items():
            if v != 1:
                print "k: %s, v: %s" % (k, v,)
        for card in self.cards():
            if card['Card Name'] not in names:
                print "%s in db and not in file" % card['Card Name']
        for name in names.keys():
            if not self.data.has_key(name):
                print "%s in file and not in db" % name

    def import_urzas_legacy_spoiler(self, fname):
        """
        This reads in a spoiler list in "Urzas Legacy" text format and populates `self.data'.
        """
        setname = "Urza's Legacy"
        s = open(fname, 'r').read()
        index = s.find("Angelic Curator")
        assert index != -1
        mo = URZAS_LEGACY_CARD_RE.search(s, index)
        while mo:
            thiscard = Card()
            thiscard['Set Name'] = setname
            self._process_key_and_val('Card Name', mo.group(1), thiscard)
            if mo.group(2) is not None:
                self._process_key_and_val('Casting Cost', mo.group(2), thiscard)
            self._process_key_and_val('Card Type', mo.group(3), thiscard)
            self._process_key_and_val('Card Rarity', mo.group(4), thiscard)
            if mo.group(5) is not None:
                self._process_key_and_val('Pow/Tou', mo.group(5), thiscard)
            self._process_key_and_val('Card Text', mo.group(6), thiscard)
            self._process_key_and_val('Illus', mo.group(7), thiscard)
            self._process_key_and_val('Card #', mo.group(8), thiscard)

            if thiscard.colors():
                self._process_key_and_val('Card Color', thiscard.colors(), thiscard)
            elif thiscard.is_artifact():
                self._process_key_and_val('Card Color', 'Artifact', thiscard)
            elif thiscard.is_land():
                self._process_key_and_val('Card Color', 'L', thiscard)

            mo = URZAS_LEGACY_CARD_RE.search(s, mo.end())

    def import_list(self, fname):
        """
        This reads in a spoiler list in any currently known Wizards of the Coast text format and populates self.data.
        """
        f = open(fname, 'r')
        id2cs = dictutil.UtilDict() # k: tuple of (set name, card number,), v: list of card objects
        setname = None
        cardstotal = None # a self-check to see if we got them all
        namesfound = dictutil.NumDict() # a self-check to see if we got them all
        incard = false
        thiscard = None
        thiskey = None
        thisval = None
        prevline = None # just for debugging
        for line in f.xreadlines():
            line = strutil.pop_trailing_newlines(line)
            mo = CARDNAME_FIELD_RE.match(line)
            if mo:
                if mo.group(5):
                    namesfound.add_num(_fixnames(mo.group(2)), int(mo.group(5)))
                else:
                    namesfound.inc(_fixnames(mo.group(2)))
                incard = true
                thiscard = Card()
                if setname:
                    thiscard['Set Name'] = setname
            if incard:
                if len(line) == 0:
                    if thiskey == 'Rarity':
                        incard = false
                        thiscard[thiskey] = thisval
                elif (line[0] in string.whitespace) or ((line.find(":") == -1) and (line.find("\t") == -1) and (line.find("  ") == -1) and ((thisval and len(thisval) > 50) or (thiskey == 'Flavor Text') or ((line[0] in string.ascii_uppercase) and (thiskey == 'Card Text')))) or (thisval and (thisval.strip()[0] == '"') and (thisval.strip()[-1] != '"') and (thiskey == 'Card Text')):
                    # Some spoiler lists have typos in which continued lines don't start with white space.  We'll assume that if this line doesn't have a separator (none of ':', '\t', or '  '), *and* if the previous line was more than 50 chars, that this is one of those typos.
                    # Some spoiler lists have typos in which attributions of quotes start on the line after the quote (in a Flavor Text field) but have no start with white space.  We'll assume that if this line begins with '-', doesn't have a separator (none of ':', '\t', or '  '), *and* if the previous line was a Flavor Text field, then this is one of those typos.
                    # Some older spoiler lists have linebreaks between lines of Card Text.  We'll assume that if the previous line was a Card Text field, and this line doesn't have a separator (none of ':', '\t', or '  '), *and* if the first character of the line is a capital letter, that this is one of those.  In addition, we'll assume that if the previous line was a Card Text field, and it began with a quote character but didn't end with one, that this is one of those.
                    assert thiskey is not None
                    assert thisval is not None
                    thisval += ' ' + line.strip()
                elif (line.find(":") == -1) and (line.find("\t") == -1) and (line.find("  ") == -1) and (line[0] in string.ascii_uppercase) and (not thiscard.has_key('Card Text')):
                    # Some spoiler lists (e.g. "Dry Spell" in homelands.txt), have typos where the "Card Text:" param name is missing!  We'll assume that if this line doesn't have a separator (none of ':', '\t', or '  '), *and* none of the previous assumptions have been taken, *and* if the first character of the line is a capital letter, *and* if there has not been any 'Card Text' field processed for this card yet, then this is one of those.
                    if thiskey:
                        self._process_key_and_val(thiskey, thisval, thiscard)
                        thiskey = None
                        thisval = None
                    thiskey = 'Card Text'
                    thisval = line
                elif RARITY_RE.match(strip_whitespace_and_quotes(line)):
                    # Some spoiler lists (e.g. "Gaea's Touch" in the_dark.txt), have typos where the "Rarity:" param name is missing!  We'll assume that if this val matches the RARITY_RE then this is one of those.
                    if thiskey:
                        self._process_key_and_val(thiskey, thisval, thiscard)
                        thiskey = None
                        thisval = None
                    thiskey = 'Rarity'
                    thisval = line
                else:
                    self._process_key_and_val(thiskey, thisval, thiscard)
                    thiskey = None
                    thisval = None

                    # on to the next key and val!
                    sepindex = line.find(':')
                    if sepindex == -1:
                        # Some spoiler lists have typos in which the ':' is missing...  So we'll break on the first occurence of two-spaces or a tab.
                        twospaceindex = line.find('  ')
                        tabindex = line.find('\t')
                        if (twospaceindex != -1) and ((twospaceindex <= tabindex) or (tabindex == -1)):
                            sepindex = twospaceindex
                        elif (tabindex != -1) and ((tabindex <= twospaceindex) or (twospaceindex == -1)):
                            sepindex = tabindex
                    assert sepindex != -1, "line: %s, line.find('\t'): %s, line.find('  '): %s" % (`line`, line.find('\t'), line.find('  '),)
                    thiskey = strip_whitespace_and_quotes(line[:sepindex])
                    thisval = line[sepindex+1:].strip()
                if thiskey == "Card #":
                    id2cs.setdefault((thiscard['Set Name'], thisval,), []).append(thiscard)
                    incard = false
                    thiscard[thiskey] = thisval
            elif (not setname) and SPOILER_NAME_RE.match(line):
                setname = SPOILER_NAME_RE.match(line).group(1)
            elif CARDS_TOTAL_RE.match(line):
                cardstotal = int(CARDS_TOTAL_RE.match(line).group(1))

            prevline = line # just for debugging

        if setname == "Antiquities":
            cardstotal -= 1 # error in antiquities.txt cardstotal, AFAICT

        if setname == "Urza's Legacy":
            # whoops -- this one is in a completely different format.
            # assert len(self.cards()) == 0 # only true if this is the first spoiler list we have loaded
            self.import_urzas_legacy_spoiler(fname)

        # Okay now fix up any obsolete or inconsistent bits.
        map(Card._update, self.cards())

        # Okay now merge any "double cards" into a single entry.
        for ((setname, cardnum,), cs,) in id2cs.items():
            if len(cs) > 1:
                assert len(cs) == 2, "len(cs): %s, cs: %s" % (len(cs), cs,)
                
                one = cs[0]
                two = cs[1]
                subone, subtwo = one['Card Name'], two['Card Name']
                for thiscard in (one, two,):
                    assert thiscard['Card Name'], thiscard.data
                    thiscard['This Card Name'] = thiscard['Card Name']
                    mo = DOUBLE_CARD_NAME_RE.match(thiscard['Card Name'])
                    if mo is not None:
                        subone, subtwo, thisone = mo.groups()
                        thiscard['This Card Name'] = thisone

                if subone != one['This Card Name']:
                    temp = one
                    one = two
                    two = temp

                newname = one['This Card Name'] + "/" + two['This Card Name']
                assert not self.has_key(newname), "newname: %s" % newname

                newc = Card(one)
                newc["Card Name"] = newname
                for k in ("Mana Cost", "Card Color", "Type & Class", "Artist",):
                    if one.get(k, "") == two.get(k, ""):
                        if one.has_key(k):
                            newc[k] = one[k]
                    else:
                        newc[k] = one.get(k,'') + "/" + two.get(k,'')

                if one.get("Card Text", "") == two.get("Card Text", ""):
                    if one.has_key("Card Text"):
                        newc["Card Text"] = one["Card Text"]
                else:
                    newc["Card Text"] = one['This Card Name'] + " -- " + one.get("Card Text",'') + "\n" + two['This Card Name'] + " -- " + two.get("Card Text",'')

                del self[one['Card Name']]
                try:
                    del self[two['Card Name']]
                except:
                    print two.data
                    print two
                    raise
                del newc['This Card Name']
                self[newname] = newc
        # print "cardstotal: %s, after merging, we had %s" % (cardstotal, len(self.cards()),)
        if (cardstotal is not None) and (cardstotal != len(self.cards())) and ((cardstotal != namesfound.sum()) or (len(self.cards()) != len(namesfound))):
            print "after merge, cardstotal: %s, namesfound.sum(): %s, len(namesfound): %s, len(self.cards()): %s" % (cardstotal, namesfound.sum(), len(namesfound), len(self.cards()),)
            # self._find_missing_names(fname)
        # assert cardstotal == len(self.cards()), "after merge cardstotal: %s, len(self.cards()): %s" % (cardstotal, len(self.cards()),)

    def export_list(self, fname):
        return self.export_list_new_and_slow(fname)

    def export_list_new_and_slow(self, fname):
        """
        This writes out the cards into a file in the "spoiler list" format.
        """
        def writecard(f, c):
            f.write(c.full_print())

        f = open(fname, "w")
        for c in self.cards():
            writecard(f, c)

LIB_RE=re.compile("\s*([0-9]*)\s*[Xx]?\s*([^ \t\n\r\f\v#]+(?: ?[^\r\n #]+)*)")

class Library(UserList.UserList):
    def __init__(self, initialdata=(), db=None):
        """
        @param db a DB() instance which must contain definitions for all the cards used
        """
        self.db = db
        UserList.UserList.__init__(self, initialdata)

    def fetch_latest_prices(self):
        for c in self.cards():
            c.fetch_latest_price()

    def sum_of_prices(self):
        sum = 0
        for c in self.cards():
            if c.get('DOLLARPRICE'):
                sum += float(c.get('DOLLARPRICE'))
        return sum

    def copy(self):
        res = Library(db=self.db)
        res.extend(self)
        return res

    def cards(self):
        return self.data[:]

    def __repr__(self):
        return string.join(map(lambda x: x["Card Name"], self), ", ")

    def __str__(self):
        return string.join(map(lambda x: x["Card Name"], self), ", ")

    def shuffle(self, seed=None):
        if seed is not None:
            randutil.seed(seed)
        randutil.shuffle(self.data)

    def import_list(self, fname):
        """
        This reads in the cards from a file in a "deck listing" format.
        """
        f = open(fname, 'r')
        
        for line in f.xreadlines():
            mo = LIB_RE.match(line)
            if mo is not None:
                numstr, name = mo.groups()
                assert type(numstr) is types.StringType, "numstr: %s :: %s, name: %s, mo.groups(): %s" % (numstr, type(numstr), name, mo.groups(),)
                if strip_whitespace_and_quotes(numstr):
                    num = int(numstr)
                else:
                    num = 1
                for i in range(num):
                    assert self.db.has_key(name), "name: %s" % `name`
                    self.append(self.db[name])

    def export_list(self, fname):
        """
        This writes out the cards into a file in a "deck listing" format.
        """
        cd = dictutil.NumDict()
        ld = dictutil.NumDict()
        sd = dictutil.NumDict()

        for c in self.cards():
            if c["Type & Class"].find("nchant") != -1:
                sd.inc(c["Card Name"])
            elif CREATURE_TYPE_AND_CLASS_RE.search(c["Type & Class"]):
                cd.inc(c["Card Name"])
            elif LAND_TYPE_AND_CLASS_RE.search(c["Type & Class"]):
                ld.inc(c["Card Name"])
            else:
                sd.inc(c["Card Name"])

        creatures = cd.items_sorted_by_value()
        creatures.reverse()
        spells = sd.items_sorted_by_value()
        spells.reverse()
        lands = ld.items_sorted_by_value()
        lands.reverse()
            
        f = open(fname, "w")
        for cn, n in creatures:
            f.write(str(n) + " " + cn + "\n")
        f.write("\n")
        for cn, n in spells:
            f.write(str(n) + " " + cn + "\n")
        f.write("\n")
        for cn, n in lands:
            f.write(str(n) + " " + cn + "\n")
        f.write("\n")

# initialize!
d = DB()

# print "sys.argv: ", sys.argv
for arg in sys.argv[1:]:
#     try:
        d.import_list(arg)
#     except exceptions.StandardError, le:
#         print humanreadable.hr(le)
#         raise le

def sort_board(b):
    ls = []
    cs = []
    os = []
    for c in b:
        if c.is_land():
            ls.append(c)
        elif c.is_creature():
            cs.append(c)
        else:
            os.append(c)
    ls.sort(cmpmanacost)
    cs.sort(cmpmanacost)
    os.sort(cmpmanacost)
    b2=ls + cs + os
    del b[:]
    b.extend(b2)

deck = Library(db=d)
hisdeck = Library(db=d)
hand = Library(db=d)
hishand = Library(db=d)
board = Library(db=d)
hisboard = Library(db=d)
grave = Library(db=d)
hisgrave = Library(db=d)
life = 20
hislife = 20

def _play(board, hand, grave, i=-1):
    c = hand.pop(i)
    print c["Card Name"]
    if not c.is_permanent():
        grave.append(c)
    else:
        board.append(c)
        sort_board(board)

def iplay(i=-1):
    return _play(board, hand, grave, i)

def hisplay(i=-1):
    return _play(hisboard, hishand, hisgrave, i)

def _draw(hand, deck):
    c = deck.pop(0)
    print c["Card Name"]
    hand.append(c)

def idraw():
    return _draw(hand, deck)

def hisdraw():
    return _draw(hishand, hisdeck)

def s():
    print "board: ", board
    print "hisboard: ", board
    print "hand: ", board
    print "hishand: ", board

PAY_1_MANA_RE=re.compile("1, TAP:.*add ((one|two|three|four|X).* mana|2|1[BGRUW]|[BGRUW][BGRUW])( or ((one|two|three|four|X).* mana|2|1[BGRUW]|[BGRUW][BGRUW]))? to your mana pool", re.IGNORECASE)
MANA_RE=re.compile("(?<![1-9BGRUW], )TAP:.*add ([1BGRUW]|(one|two|three|four|X).* mana)( or ([1BGRUW]|(one|two|three|four|X).* mana))? to your mana pool|^\[[BGRUW]\]$", re.IGNORECASE)
SLOW_RE=re.compile("comes into play tapped", re.IGNORECASE)
DEPENDS_RE=re.compile("Play this ability only if you control a ([A-Z]*)", re.IGNORECASE)

def _measuremana(tdeck, n):
    m=0
    for c in tdeck[:(n-1)]:
        if MANA_RE.search(c["Card Text"]):
            # print "MANA_RE: ", c["Card Name"]
            m+=1
    c = tdeck[n-1]
    if MANA_RE.search(c["Card Text"]) and not SLOW_RE.search(c["Card Text"]) and not c.is_creature():
        # print "last MANA_RE: ", c["Card Name"]
        mo = DEPENDS_RE.search(c["Card Text"])
        if mo:
            if len(filter(lambda x, mo=mo: x["Card Name"].lower() == mo.group(1), tdeck[:n])) > 0:
                m+=1
        else:
            m+=1
    for c in tdeck[:n]:
        if PAY_1_MANA_RE.search(c["Card Text"]):
            # print "PAY_1_MANA_RE: ", c["Card Name"]
            mo = DEPENDS_RE.search(c["Card Text"])
            if mo:
                if len(filter(lambda x, mo=mo: x["Card Name"].lower() == mo.group(1), tdeck[:n])) > 0:
                    if m>=1:
                        m+=1
            else:
                if m>=1:
                    m+=1
    for c in tdeck[:n]:
        if c["Card Name"] == "Cabal Coffers":
            # print "Cabal Coffers: ", c["Card Name"]
            mo = DEPENDS_RE.search(c["Card Text"])
            if mo:
                if len(filter(lambda x, mo=mo: x["Card Name"].lower() == mo.group(1), tdeck[:n])) > 0:
                    if m>=2:
                        m+=1
            else:
                if m>=2:
                    m+=max(len(filter(lambda c: c["Card Name"] == "Swamp", tdeck[:n]))-2,0)
    return m

def _screwage(tdeck, turn=0, draw=0):
    return len(filter(lambda c: c.converted_mana_cost() > min(_measuremana(tdeck, turn+7+draw), turn), tdeck[:turn+7+draw]))

def measure_screwage(tdeck, turns=6, draw=0):
    for t in range(turns):
        print "turn %s, screwage %s" % (t, _screwage(tdeck, t, draw),)

def sum_screwage(tdeck, maxturns=6, draw=0):
    return reduce(operator.__add__, map(_screwage, [tdeck]*maxturns, range(maxturns), [draw]*maxturns), 0)

def ave_screwage(tdeck, maxturns=6, draw=0):
    sum = 0
    r = 2**5
    for i in range(r):
        tdeck.shuffle(i)
        sum += sum_screwage(tdeck, maxturns, draw)
    return float(sum) / r

def testmana(tdeck, iters=2**10):
    tot10 = 0
    tot13 = 0
    screwle0_10 = 0
    screwle1_10 = 0
    screwle2_10 = 0
    atleast2_10 = 0
    succs10 = 0
    succs13 = 0
    r=iters
    for i in range(r):
        tdeck.shuffle(r)
        res10 = _measuremana(tdeck, 10)
        tot10 += res10
        if res10 >= 3:
            succs10+=1
        if res10 <= 0:
            screwle0_10+=1
        if res10 <= 1:
            screwle1_10+=1
        if res10 <= 2:
            screwle2_10+=1
        if res10 >= 2:
            atleast2_10+=1
        res13 = _measuremana(tdeck, 13)
        assert res13 >= res10
        if res13 >= 4:
            succs13+=1
        tot13 += res13

    print "ave in 10 cards: %0.1f, chance <= 0 in 10 cards: %0.2f, chance <= 1 in 10 cards: %0.2f, chance <= 2 in 10 cards: %0.2f, chance >= 2 in 10 cards: %0.2f, chance >= 3 in 10 cards: %0.2f, ave in 13 cards: %0.1f, chance >= 4 in 13 cards: %0.2f" % (float(tot10)/r, float(screwle0_10)/r, float(screwle1_10)/r, float(screwle2_10)/r, float(atleast2_10)/r, float(succs10)/r, float(tot13)/r, float(succs13)/r,)

code.interact("mtgspoiler", None, locals())

__setupstr="""
SEED=64
MYDECK="mine/W_clerics.deck"
HISDECK="others/psych-pt-chicago-2003.deck"
deck.import_list(MYDECK)
hisdeck.import_list(HISDECK)
deck.shuffle(SEED)
hisdeck.shuffle(SEED+1)
randutil.randrange(0, 2)
h=hand
ip=iplay
b=board
g=grave
hd=hisdraw
hh=hishand
hp=hisplay
hb=hisboard
hg=hisgrave
#testmana(deck)
#testmana(hisdeck)
for i in range(7):
    idraw()

for i in range(7):
    hd()

"""

# Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software to deal in this software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of this software, and to permit
# persons to whom this software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of this software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
