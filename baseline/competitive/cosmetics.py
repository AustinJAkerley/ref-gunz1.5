"""Install progression-free UI and a server-authoritative GBucks catalogue.

Integration: data.install_items must call install(data_root, output_root) LAST,
after writing the basic ring/world item overlays. output_root is a disposable
staging tree with client/ and server/; this module never reads a database.
runtime must copy the resulting system/, Interface/default/ and server/shop.xml
overlays, not just zitem.xml. Input caches must never be used as the output.
"""
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
from xml.parsers import expat


ITEM_NAMESPACE = 'http://tempuri.org/zitem.xsd'
SLOTS = ('head', 'chest', 'hands', 'legs', 'feet')
PRICE = 100
# Existing IDs, complete male/female sets, with assets in the pinned pack.
OUTFITS = {
    'Magician': {'f': tuple(range(48011, 48016)), 'm': tuple(range(48016, 48021))},
    'Halem': {'f': tuple(range(48021, 48026)), 'm': tuple(range(48026, 48031))},
    'Crusader': {'f': tuple(range(48071, 48076)), 'm': tuple(range(48076, 48081))},
    'Ninja': {'f': tuple(range(48081, 48086)), 'm': tuple(range(48086, 48091))},
}
CATALOGUE_IDS = tuple(i for sexes in OUTFITS.values() for ids in sexes.values() for i in ids)
ARMOR_STATS = dict(hp='4', ap='20', weight='0', maxwt='0', sf='0', fr='0',
                   cr='0', pr='0', lr='0', res_level='0')
SALE_MESSAGE = 'Selling is disabled. Keep your free starter gear; GBucks buy cosmetics only.'

# Numeric message IDs are the existing ZMsg(MSG_*) mappings, not new messages.
# These are NOT a conversion of XP into currency. Keep the obsolete IDs empty:
# rapidxml value() returns a non-null empty string for <MSG id="..." /> and
# MStringRes::Initialize stores it via MXmlNode::GetText (covered by a fixture).
MESSAGES = {
    '1304': '', '1703': '', '1717': '', '1712': '', '1713': 'GBucks',
    '2002': '', '2003': '', '2022': SALE_MESSAGE,
    '9303': '', '9346': '', '9366': '',
}
STRINGS = {
    'UI_LOBBY_08': '', 'UI_LOBBY_09': '', 'UI_LOBBY_10': 'GBucks : 0',
    'UI_STAGE_03': '', 'UI_STAGE_04': '', 'UI_STAGE_05': 'GBucks : -',
    'UI_STAGE_18': '', 'UI_CS_02': '', 'UI_SSF_05': '',
    'UI_EQUIPMENT_08': '[ HP / AP ]', 'UI_ETC_02': '',
    'UI_SHOP_07': SALE_MESSAGE, 'UI_SHOP_08': SALE_MESSAGE,
    'UI_SHOP_09': SALE_MESSAGE, 'UI_SHOP_10': '[ GBucks ]',
    'UI_SHOP_11': '0 GBucks', 'UI_SHOP_12': '[ WEIGHT ]',
    'UI_SHOP_14': 'Selling disabled', 'UI_SHOP_15': SALE_MESSAGE,
    'UI_SHOP_17': 'Selling disabled',
    'UI_CLAN_12': 'Clan creation costs 1000 GBucks and requires four founding members. Choose a unique name up to 13 letters.',
}
HIDDEN_WIDGETS = {
    'Lobby_PlayerSpecLevel', 'Lobby_PlayerSpecXP', 'Stage_PlayerSpecLevel',
    'Stage_PlayerSpecXP', 'Stage_QuestLevel', 'Stage_QuestLevelBG', 'StageLevelLimit',
    'CharSel_Level0', 'CharSel_Level1', 'CharSel_Level2', 'CharSel_Level3',
    'QuestResult_GetPlusXP', 'QuestResult_GetMinusXP', 'QuestResult_GetTotalXP',
    'MyAllEquipmentListCaller', 'Shop_FrameTabLabel2', 'SellConfirmCaller',
    'SellQuestItemConfirmCaller', 'Shop_SellQuestItem',
}
UI_FILES = ('Lobby.xml', 'Stage.xml', 'CharSelection.xml', 'StageSettingFrame.xml',
            'Shop.xml', 'Equipment.xml', 'GameResult.xml')
TEXT_FILES = ('strings.xml', 'messages.xml', 'cserror.xml', 'tips.xml')
HUD_ART = 'client/Interface/default/combat/hp.tga.dds'
# Inspected pinned 512x256 texture: baked "Lv. 25. TAIGETUS.." and EXP track.
# Keep the two HP/AP tracks and their frame. DXT3 stores explicit 4-bit alpha.
HUD_ERASE_RECTS = ((132, 22, 424, 51), (150, 149, 490, 179))


def _hud_art(source):
    blob = bytearray(source.read_bytes())
    if (blob[:4] != b'DDS ' or blob[84:88] != b'DXT3'
            or struct.unpack_from('<II', blob, 12) != (256, 512)
            or len(blob) != 128 + 512 * 256):
        raise ValueError('Unexpected pinned HUD DDS; review progression artwork')
    for left, top, right, bottom in HUD_ERASE_RECTS:
        for y in range(top, bottom):
            for x in range(left, right):
                block = 128 + ((y // 4) * 128 + x // 4) * 16
                pixel = (y % 4) * 4 + x % 4
                blob[block + pixel // 2] &= ~(15 << (4 * (pixel % 2)))
    return bytes(blob)


def literal_names(xml):
    """Names as seen by MXmlDocument/rapidxml (namespace processing OFF)."""
    names = []
    parser = expat.ParserCreate()
    parser.StartElementHandler = lambda name, attrs: names.append(name)
    parser.Parse(xml, True)
    return names


def _xml_bytes(tree):
    root = tree.getroot()
    # Register the root's ORIGINAL default namespace only. The UI's standalone
    # Schema child has a different default; prefix that unused child rather than
    # accidentally putting the whole UI document in the schema namespace.
    ET.register_namespace('schema', 'MaietData')
    if root.tag.startswith('{'):
        ET.register_namespace('', root.tag[1:].split('}', 1)[0])
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    names = literal_names(data)
    if not names or names[0].lower() != 'xml':
        raise ValueError('Legacy XML root must be literally XML/xml, not a prefixed name')
    if root.tag == '{' + ITEM_NAMESPACE + '}XML' and any(n != 'ITEM' for n in names[1:]):
        raise ValueError('Item names must be literal ITEM for the real loader')
    return data


def _items(path):
    tree = ET.parse(path)
    if tree.getroot().tag != '{' + ITEM_NAMESPACE + '}XML':
        raise ValueError(f'Unexpected item root/default namespace: {path}')
    items = {}
    for e in tree.getroot():
        if e.tag != '{' + ITEM_NAMESPACE + '}ITEM':
            raise ValueError('Unexpected item element')
        ident = int(e.attrib['id'])
        if ident in items:
            raise ValueError(f'Duplicate item ID {ident}')
        items[ident] = e
    return tree, items


def validate(data_root):
    """Fail closed on changed IDs, gender, slots, assets or starter stats."""
    data_root = Path(data_root)
    _, client = _items(data_root / 'client/system/zitem.xml')
    _, server = _items(data_root / 'server/zitem.xml')
    if len(set(CATALOGUE_IDS)) != 40:
        raise ValueError('Catalogue IDs must be unique')
    for sex, directory in (('m', 'man'), ('f', 'woman')):
        model = data_root / f'client/Model/{directory}'
        # ZApplication loads character.xml for gameplay AND character selection;
        # character_lobby.xml is unused and lacks even the existing starter set.
        # The active descriptors have duplicate sound attributes in animations,
        # accepted by rapidxml, so validate only their well-formed AddParts tags.
        descriptor = (model / f'{directory}01.xml').read_text(encoding='utf-8')
        descriptor = re.sub(r'<!--.*?-->', '', descriptor, flags=re.S)
        parts = re.findall(r'<AddParts\b[^>]*>', descriptor)
        if not parts:
            raise ValueError('Missing character model part references')
        assets = []
        for tag in parts:
            node = ET.fromstring(tag[:-1].rstrip('/ ') + '/>')
            part = model / node.attrib['filename']
            if not part.is_file():
                raise ValueError(f'Missing pinned model part {part}')
            assets.append(part.read_bytes().lower())
        for family, sexes in OUTFITS.items():
            for ident, slot in zip(sexes[sex], SLOTS):
                item = client[ident]
                if item.attrib != server[ident].attrib:
                    raise ValueError(f'Client/server cosmetic mismatch: {ident}')
                if (item.get('res_sex'), item.get('slot'), item.get('type')) != (sex, slot, 'equip'):
                    raise ValueError(f'Wrong cosmetic slot/sex: {ident}')
                if 'admin' in (item.get('name', '') + item.get('desc', '')).lower():
                    raise ValueError('Admin cosmetics forbidden')
                mesh = item.get('mesh_name', '').lower().encode('ascii')
                if not mesh or not any(mesh + b'\0' in blob for blob in assets):
                    raise ValueError(f'{family} {sex}/{slot}: mesh missing from loaded character parts')
        starter = range(48001 if sex == 'm' else 48002, 48011, 2)
        for ident, slot in zip(starter, SLOTS):
            item = client[ident]
            if item.attrib != server[ident].attrib or item.get('slot') != slot:
                raise ValueError('Starter appearance must agree client/server')
            if any(item.get(k) != v for k, v in ARMOR_STATS.items()):
                raise ValueError('Valkyrie baseline stats changed')
    return client


def _replace_currency(text):
    return re.sub(r'\b(?:bounty|BP)\b', 'GBucks', text, flags=re.IGNORECASE)


def _text_tree(source):
    tree = ET.parse(source)
    # Tips are nested TIPS/MSG, unlike the flat string/message tables.
    for e in tree.getroot().iter():
        ident, original = e.get('id'), e.text or ''
        text = _replace_currency(original)
        if source.name == 'messages.xml' and ident in MESSAGES:
            text = MESSAGES[ident]
        elif source.name == 'strings.xml' and ident in STRINGS:
            text = STRINGS[ident]
        elif source.name == 'cserror.xml' and ident in ('20005', '20006', '20007', '20014'):
            text = SALE_MESSAGE
        elif ident and ident.startswith('CHANNEL_'):
            text = re.sub(r'\s*\([^)]*[Ll]evel[^)]*\)', '', text)
            text = text.replace('Entry-level', 'Open')
        elif ident == 'ZITEM_DESC_525004':
            text = 'Legacy accessory. No reward bonuses in competitive play.'
        elif ident == 'ZITEM_DESC_509006':
            text = 'Breaker 9 series shotgun made by Rionix.'
        elif source.name == 'tips.xml' and re.search(
                r'\b(?:exp|xp|experience points|level\s+\d+|level (?:difference|restriction))\b', text, re.I):
            text = 'GBucks buy cosmetic outfits. Every outfit piece has the same stats as your free starter gear.'
        elif source.name == 'cserror.xml' and re.search(r'\blevel\b', text, re.I):
            # Obsolete compatibility error IDs are kept so the real table loads.
            text = 'This action is unavailable.'
        # Enchantment tiers, map names and descriptive "level of accuracy" are
        # not character progression; don't erase that unrelated terminology.
        e.text = text
    return tree


def _ui_tree(source):
    tree = ET.parse(source)
    root = tree.getroot()
    removed = set(HIDDEN_WIDGETS)
    # Remove descendants by Mint's parent attribute, not only XML nesting.
    while True:
        more = {e.get('item') for e in root if e.get('parent') in removed and e.get('item')}
        if more <= removed:
            break
        removed |= more
    for e in list(root):
        name = e.get('item', '')
        if name in removed or e.findtext('TEXT') == 'STR:UI_SSF_05':
            root.remove(e)
        elif source.name == 'GameResult.xml' and 'PlayerScore' in name:
            # The score widgets contain XP, not ladder points. The shared result
            # background is retained; presentation_patch replaces only quest art.
            # Their call sites check FindWidget for null before setting values.
            root.remove(e)
    if source.name == 'Shop.xml':
        label = ET.SubElement(root, 'LABEL', item='CompetitiveCosmeticNotice', parent='Shop')
        ET.SubElement(label, 'FONT').text = 'FONTa9'
        bounds = ET.SubElement(label, 'BOUNDS')
        for k, v in dict(X=20, Y=535, W=760, H=18).items():
            ET.SubElement(bounds, k).text = str(v)
        ET.SubElement(label, 'TEXT').text = 'Cosmetics: 100 GBucks/piece, 500 per full outfit. Selling is disabled.'
    if source.name == 'GameResult.xml':
        label = ET.SubElement(root, 'LABEL', item='CompetitiveQuestGBucks', parent='QuestResult')
        ET.SubElement(label, 'FONT').text = 'FONTa10b'
        bounds = ET.SubElement(label, 'BOUNDS')
        for k, v in dict(X=40, Y=222, W=125, H=20).items():
            ET.SubElement(bounds, k).text = str(v)
        ET.SubElement(label, 'TEXT').text = 'GBucks'
    return tree


def install(data_root, output_root):
    """Overlay a disposable data.py output, preserving the installed Basic Ring.

    Re-running is deterministic. All bytes are validated before output writes.
    Never call directly against an existing game runtime or original data tree.
    """
    data_root, output_root = Path(data_root).resolve(), Path(output_root).resolve()
    if output_root == data_root or data_root in output_root.parents or output_root in data_root.parents:
        raise ValueError('Cosmetics require a separate staging output tree')
    if output_root.name == 'reference-runtime':
        raise ValueError('Install to staging, never the live game runtime')
    pinned = validate(data_root)
    outputs = {}
    for relative in ('client/system/zitem.xml', 'server/zitem.xml'):
        target = output_root / relative
        # data.py has already installed ring 25011; retain it (and nothing from DB).
        tree, items = _items(target if target.exists() else data_root / relative)
        for item in items.values():
            item.set('res_level', '0')
            if item.get('slot') in SLOTS:
                item.attrib.update(ARMOR_STATS)
                # No hidden armor movement, combat, reward or carrying bonuses.
                for key in ('damage', 'delay', 'maxbullet', 'magazine', 'reloadtime',
                            'limitjump', 'limittumble', 'limitwall', 'xp_bonus', 'bp_bonus',
                            'xp_solo_bonus', 'xp_team_bonus', 'bp_solo_bonus', 'bp_team_bonus', 'totalpoint'):
                    if key in item.attrib:
                        item.set(key, '0')
                if 'limitspeed' in item.attrib:
                    item.set('limitspeed', '100')
        for family, sexes in OUTFITS.items():
            for sex, ids in sexes.items():
                for ident in ids:
                    item = items[ident]
                    if item.get('mesh_name') != pinned[ident].get('mesh_name'):
                        raise ValueError('Staged cosmetic appearance drift')
                    item.set('iscashitem', 'false')
                    item.set('bt_price', str(PRICE))
                    item.set('desc', f'{family} cosmetic. Same stats as the free Valkyrie starter. 100 GBucks per piece; 500 per outfit. Not sellable.')
        outputs[relative] = _xml_bytes(tree)
    # The server's actual shop loader uses XML/SELL/itemid. Never advertise
    # legacy power items or duplicate the already-free starter inventory.
    shop = ET.Element('XML', id='shop')
    for ident in CATALOGUE_IDS:
        ET.SubElement(shop, 'SELL', itemid=str(ident))
    outputs['server/shop.xml'] = _xml_bytes(ET.ElementTree(shop))
    # fg_zitem.xml is a separate optional descriptor set. Strip every requirement
    # there too without substituting its gameplay definitions for the real set.
    relative = 'client/system/fg_zitem.xml'
    # This legacy replay table declares UTF-8 but contains Windows-1252 quotes.
    # Decode its pinned bytes correctly before serializing valid UTF-8/default NS.
    raw = (data_root / relative).read_bytes()
    try:
        decoded = raw.decode('utf-8')
    except UnicodeDecodeError:
        decoded = raw.decode('cp1252')
    tree = ET.ElementTree(ET.fromstring(decoded))
    for e in tree.getroot():
        e.set('res_level', '0')
        # Replay-only reward/requirement prose, not skill tiers or item lore.
        if re.search(r'\b(?:xp|exp|level restriction|required level)\b', e.get('desc', ''), re.I):
            e.set('desc', 'Legacy replay item. No progression rewards.')
        if re.search(r'\b(?:xp|exp)\b', e.get('name', ''), re.I):
            e.set('name', re.sub(r'\b(?:xp|exp)\s*', '', e.get('name'), flags=re.I))
    outputs[relative] = _xml_bytes(tree)
    outputs[HUD_ART] = _hud_art(data_root / HUD_ART)
    for base in ('client/system', 'server'):
        for name in TEXT_FILES:
            source = data_root / base / name
            if source.is_file():
                outputs[f'{base}/{name}'] = _xml_bytes(_text_tree(source))
    for name in UI_FILES:
        relative = f'client/Interface/default/{name}'
        outputs[relative] = _xml_bytes(_ui_tree(data_root / relative))
    for relative, content in outputs.items():
        target = output_root / relative
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != output_root.parent):
            raise ValueError('Refusing symlinked overlay destination')
    for relative, content in outputs.items():
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return tuple(outputs)