#!/usr/bin/env python
#
# Copyright (c) 2002 Bryce "Zooko" Wilcox-O'Hearn
# mailto:zooko@zooko.com
# See the end of this file for the free software, open source license (BSD-style).

# CVS:
__cvsid = '$Id: mtgspoiler.py,v 1.5 2002/03/04 22:02:22 zooko Exp $'

# HOWTO:
# 1. Get pyutil from `http://sf.net/projects/pyutil'.
# 2. Get mtgspoiler from `http://sf.net/projects/mtgspoiler'.
# 3. Get spoiler lists from `http://www.wizards.com/default.asp?x=magic/products/cardlists,,en'.
# 4. Run this command line:
# /path/to/pyutil/pstart '$PYTHON -i /path/to/mtgspoiler/mtgspoiler.py /path/to/spoiler.txt /path/to/next_spoiler.txt''
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

# standard modules
import UserList, copy, random, re, string, sys, types

# pyutil modules (http://sf.net/projects/pyutil)
import strutil
import dictutil
import VersionNumber

# major, minor, micro (== bugfix release), nano (== not-publically-visible patchlevel), flag (== not-publically-visible UNSTABLE or STABLE flag)
versionobj = VersionNumber.VersionNumber(string.join(map(str, (0, 0, 5, 2,)), '.') + '-' + 'UNSTABLE')

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
    return cmp(xc, yc)

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
            mc = mc[:mc.find("/")] # ??? for double-cards.
        for char in mc:
            if char in "BGRUW":
                cc+=1
            else:
                num += char
        cc += int(num)
        return cc

    def colored_mana_cost(self):
        mc = self.get("Mana Cost", '0')
        if mc.find("/") != -1:
            mc = mc[:mc.find("/")] # ??? for double-cards.
        return filter(lambda c: c in "BGRUW", mc)

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
            if len(filter(lambda color: color in card.get('Mana Cost', ''), colors)) > 0:
                del self[name]

    def filter_in_colors(self, colors='RGWUB'):
        for name, card in self.items():
            if len(filter(lambda color: color in card.get('Mana Cost', ''), colors)) == 0:
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
                        if thisval.strip() == "n/a":
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

                    if thiskey is not None:
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

LIB_RE=re.compile("\s*([0-9]*)\s*[Xx]?\s*(\S+.*)")

class Library(UserList.UserList):
    def __init__(self, db, initialdata=()):
        """
        @param db a DB() instance which must contain definitions for all the cards used
        """
        self.db = db
        self.data = []
        self.data.extend(initialdata)
        pass

    def cards(self):
        return self.data[:]

    def __repr__(self):
        return string.join(map(lambda x: x["Card Name"], self), ", ")

    def __str__(self):
        return string.join(map(lambda x: x["Card Name"], self), ", ")

    def shuffle(self):
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
                    assert self.db.has_key(name), "name: %s" % name
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
            elif c["Type & Class"].find("reature") != -1:
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
