#!/usr/bin/env python
#
# Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
# mailto:zooko@zooko.com
# See the end of this file for the free software, open source license (BSD-style).

# CVS:
__cvsid = '$Id: mtgspoiler.py,v 1.7 2002/03/21 18:40:29 zooko Exp $'

# HOWTO:
# 1. Get pyutil from `http://sf.net/projects/pyutil'.
# 2. Get mtgspoiler from `http://sf.net/projects/mtgspoiler'.
# 3. Get spoiler lists from `http://www.wizards.com/default.asp?x=magic/products/cardlists,,en'.
# 4. Run this command line:
# /path/to/pyutil/pstart /path/to/mtgspoiler/mtgspoiler.py /path/to/spoiler.txt /path/to/next_spoiler.txt
# 5. Now you're in a Python interpreter with a local object named `d' containing the spoiler
#    database.  If you haven't already, learn Python from
#    `http://python.sourceforge.net/devel-docs/tut/tut.html'.  Assuming you are a hacker, this will
#    take only a couple of hours and can be enjoyably interlaced with the rest of these steps.
# 6. This Python command prints out all the cards in the database:
# d
# 7. This Python command assigns (newly created) local variable `c' to reference the first card in
# the database:
# c = d.cards()[0]
# 8. This one assigns `c' to reference the card named "Granite Grip".
# c = d['Granite Grip']
# 9. This Python command prints out this card:
# c
# 10. This Python command will tell you all the methods that you can invoke on `d':
# dir(d)
# 11. And this one tell you all the methods that you can invoke on `c':
# dir(c)
# 12. This one removes all cards have colored mana in their casting costs:
# d.filter_out_colors()
# 13. Now here is a cool and complicated one.  You'll have to read the inline docs for what it does.
# hosers = d.filter_in_useful_for_playing_colors("BU")
# 14. Okay, now please add features and submit patches.  Thanks!  --Zooko 2002-03-01


# TODO:
# * import "Oracle" errata and apply them...
# * merge double cards via number and not name (ap_spoiler doesn't have double-card names...)

# standard modules
import UserList, code, copy, operator, random, re, string, sys, types

# pyutil modules (http://sf.net/projects/pyutil)
import strutil
import dictutil
import VersionNumber

# major, minor, micro (== bugfix release), nano (== not-publically-visible patchlevel), flag (== not-publically-visible UNSTABLE or STABLE flag)
versionobj = VersionNumber.VersionNumber(string.join(map(str, (0, 0, 7, 0,)), '.') + '-' + 'UNSTABLE')

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
    "Casting Cost": "Mana Cost",
    "Card Type": "Type & Class",
    }

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
        # Different spoiler lists do different things for the "Mana Cost" of a land.  What *we* do is remove it from the dict entirely.
        # (When exporting a spoiler list, it will be printed as "n/a", which is how the Torment spoiler list did it.)
        if LAND_TYPE_AND_CLASS_RE.search(self["Type & Class"]):
            self.del_if_present("Mana Cost")

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
        for k in ks:
            s = formfield(s, k, self[k])
            ks.remove(k)

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
        res += ' ' + RARITY_NAME_MAP[self['Rarity']] + '\n'
        ks.remove('Rarity')
        if self['Card Text']:
            res += self['Card Text'] + '\n'
        ks.remove('Card Text')
        if includeflavortext and self.get('Flavor Text'):
            res += self['Flavor Text'] + '\n'
        if 'Flavor Text' in ks:
            ks.remove('Flavor Text')
        if includeartist:
            res += self['Artist'] + '\n'
        ks.remove('Artist')
        if includecardcolor:
            res += self['Card Color'] + '\n'
        ks.remove('Card Color')
        if includecardnumber:
            res += self['Card #'] + '\n'
        ks.remove('Card #')

        for k in ks:
            if self[k]:
                res += k + ': ' + self[k] + '\n'

        return res

DOUBLE_CARD_NAME_RE=re.compile("(.*)/(.*) \(.*\)")
LAND_TYPE_AND_CLASS_RE=re.compile("(?<![Ee]nchant )[Ll]and")
CREATURE_TYPE_AND_CLASS_RE=re.compile("(?<![Ee]nchant )[Cc]reature")
ENCHANTMENT_TYPE_AND_CLASS_RE=re.compile("[Ee]nchant")
ARTIFACT_TYPE_AND_CLASS_RE=re.compile("(?<![Ee]nchant )[Aa]rtifact")
INSTANT_TYPE_AND_CLASS_RE=re.compile("[Ii]nstant|[Ii]nterrupt")
INSTANT_CARD_TEXT_RE=re.compile("[Yy]ou may play .* any time you could play an instant")

class DB(dictutil.UtilDict):
    def __init__(self, initialdata={}, importfile=None):
        # k: cardname, v: {}
        dictutil.UtilDict.__init__(self, initialdata)
        if importfile is not None:
            self.import_list(importfile)

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
    
    def filter_in_affects_color_or_basic_land(self, colors="BGRUW"):
        """
        Removes all cards which do not mention colors by name (i.e. "white", not "W" nor "[W]", which both denote mana) nor the associated basic land (i.e. "Plains").
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

    def filter_in_useful_for_playing_colors(self, colors="BGRUW"):
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

    def import_list(self, fname):
        """
        This reads in a spoiler list in Wizards of the Coast text format and populates `self.data'.
        """
        f = open(fname, 'r')
        setname = None
        incard = false
        thiscard = None
        thiskey = None
        thisval = None
        for line in f.xreadlines():
            line = strutil.pop_trailing_newlines(line)
            if line[:len("Card Name:")] == "Card Name:":
                incard = true
                thiscard = Card()
                if setname:
                    thiscard['Set Name'] = setname
            elif line[:len("Card Title:")] == "Card Title:":
                incard = true
                thiscard = Card()
                if setname:
                    thiscard['Set Name'] = setname
            if incard:
                assert len(line) > 0
                # some spoiler lists have typos in which continued lines don't start with white space.  We'll assume that if this line doesn't have a separator (none of ':', '\t', or '  '), *and* if the previous line was more than 50 chars, that this is one of those typos.
                if (line[0] in string.whitespace) or ((line.find(":") == -1) and (line.find("\t") == -1) and (line.find("  ") == -1) and (len(thisval) > 50)):
                    assert thiskey is not None
                    assert thisval is not None
                    thisval += ' ' + line.strip()
                else:
                    thiskey = UPDATE_NAMES.get(thiskey, thiskey)
                    if thiskey == "Card Name":
                        self.data[thisval.strip()] = thiscard
                    elif thiskey == "Pow/Tou":
                        if thisval.strip().lower() == "n/a":
                            thisval = ""
                        if thisval.find('/') != -1:
                            try:
                                thiscard['Pow'] = int(thisval[:thisval.find('/')].strip())
                            except ValueError:
                                # Oh, this must be a "special" Pow.
                                thiscard['Pow'] = thisval[:thisval.find('/')].strip()
                            try:
                                thiscard['Tou'] = int(thisval[thisval.find('/')+1:].strip())
                            except ValueError:
                                # Oh, this must be a "special" Tou.
                                thiscard['Tou'] = thisval[thisval.find('/')+1:].strip()

                    if thiskey:
                        thiscard[thiskey] = thisval.strip()
                        # assert not ((thiskey == "Mana Cost") and (thisval.strip().find("and") != -1)), "thiscard.data: %s, thiskey: %s, thisval: %s" % (thiscard.data, thiskey, thisval,) # we fix this in "_update()".
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
                    thiskey = line[:sepindex].strip()
                    thisval = line[sepindex+1:].strip()
                if thiskey == "Card #":
                    incard = false
                    thiscard[thiskey] = thisval
            elif (not setname) and (line.find("Spoiler") != -1):
                setname = line[:line.find("Spoiler")-1]

        # Okay now merge any "double cards" into a single entry. (and also fix up any obsolete or inconsistent bits)
        for c in self.cards():
            c._update()

            mo = DOUBLE_CARD_NAME_RE.match(c["Card Name"])
            if mo is not None:
                subone, subtwo = mo.groups()
                newname = subone + "/" + subtwo
                if self.has_key(newname):
                    continue # already did this one
                onename = newname + " (" + subone + ")"
                twoname = newname + " (" + subtwo + ")"
                assert (onename == c["Card Name"]) or (twoname == c["Card Name"])
                one = self[onename]
                two = self[twoname]

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
                    newc["Card Text"] = subone + " -- " + one.get("Card Text",'') + "\n" + subtwo + " -- " + two.get("Card Text",'')

                self[newname] = newc
                del self[onename]
                del self[twoname]

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

    def export_list_old_and_fast(self, fname):
        """
        This writes out the cards into a file in the "spoiler list" format.
        """
        def writecard(f, c):
            def writefield(f, k, v):
                f.write(k+':')
                if len(k) < 7:
                    f.write('\t')
                f.write('\t')
                fv = v.replace(v, "\n", "\n\t\t")
                f.write(fv)
                f.write('\n')

            ks = c.keys()
            for k in ("Card Name", "Card Color", "Mana Cost", "Type & Class", "Pow/Tou", "Card Text", "Flavor Text", "Artist", "Rarity"):
                if c.has_key(k):
                    writefield(f, k, c[k])
                    ks.remove(k)

            if "Pow" in ks:
                ks.remove("Pow")
            if "Tou" in ks:
                ks.remove("Tou")
            if "Card #" in ks:
                ks.remove("Card #")
            for k in ks:
                writefield(f, k, c[k])
                ks.remove(k)

            writefield(f, "Card #", c["Card #"])
            f.write("\n")

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
            random.seed(seed)
        random.shuffle(self.data)

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
                if numstr.strip():
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
    d.import_list(arg)

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

import random
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

def testmana(tdeck):
    tot10 = 0
    tot13 = 0
    succs10 = 0
    succs13 = 0
    r=2**10
    for i in range(r):
        tdeck.shuffle(r)
        res10 = _measuremana(tdeck, 10)
        tot10 += res10
        if res10 >= 3:
            succs10+=1
        res13 = _measuremana(tdeck, 13)
        assert res13 >= res10
        if res13 >= 4:
            succs13+=1
        tot13 += res13

    print "ave in 10 cards: %s, chance >= 3 in 10 cards: %s, ave in 13 cards: %s, chance >= 4 in 13 cards: %s" % (float(tot10)/r, float(succs10)/r, float(tot13)/r, float(succs13)/r,)

code.interact("mtgspoiler", None, locals())

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
