"""Progression-free access and presentation for the disposable source stage.

Compose AFTER patch_source.changes and economy_patch.changes. No wire fields or
database balances are renamed here. This module deliberately does not own the
scoreboard/result renderer (ZCombatInterface.cpp), combat, controls, or economy.
Keep internal level/XP compatibility floors and Elo untouched. Patch only the
stage copy via FILES/changes; this module has no disk or runtime side effects.
"""


def block_span(text, anchor):
    """Find one anchored C++ body, respecting quoted literals and comments.

    Deliberately not a regex over nested braces. An upstream signature change,
    duplicate anchor, or unterminated body fails before any output is written.
    """
    if text.count(anchor) != 1:
        raise ValueError(f'Expected one body anchor: {anchor!r}')
    start = text.index(anchor) + len(anchor)
    while start < len(text) and text[start].isspace():
        start += 1
    if text[start:start + 1] != '{':
        raise ValueError(f'Expected opening brace after {anchor!r}')
    depth, state, i = 0, 'code', start
    while i < len(text):
        c, pair = text[i], text[i:i + 2]
        if state in ('"', "'"):
            if c == '\\':
                i += 2
                continue
            if c == state:
                state = 'code'
        elif state == 'line':
            if c == '\n':
                state = 'code'
        elif state == 'comment':
            if pair == '*/':
                state = 'code'
                i += 2
                continue
        elif pair in ('//', '/*'):
            state = 'line' if pair == '//' else 'comment'
            i += 2
            continue
        elif c in ('"', "'"):
            state = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    raise ValueError(f'Unterminated body: {anchor!r}')


def changes(relative, text):
    def replace(old, new, count=1):
        nonlocal text
        if text.count(old) != count:
            raise ValueError(f'{relative}: expected {count} matches for {old[:100]!r}, got {text.count(old)}')
        text = text.replace(old, new)

    def body(signature, replacement, requires=()):
        nonlocal text
        start, end = block_span(text, signature)
        previous = text[start:end]
        if previous == '{\n' + replacement + '\n}':
            raise ValueError(f'{relative}: body already patched: {signature}')
        for expected in requires:
            if expected not in previous:
                raise ValueError(f'{relative}: missing body contract {expected!r}')
        text = text[:start] + '{\n' + replacement + '\n}' + text[end:]

    def remove_block(anchor, requires=()):
        nonlocal text
        start, end = block_span(text, anchor)
        for expected in requires:
            if expected not in text[start:end]:
                raise ValueError(f'{relative}: missing removal contract {expected!r}')
        text = text[:text.index(anchor)] + '// No character-progression restriction or display.\n' + text[end:]

    if relative == 'Gunz/ZGameInterface.cpp':
        replace('''		// LV
		pLabel = (MLabel*)pRes->FindWidget("Lobby_PlayerSpecLevel");
		sprintf_safe(buf, "%s : %d %s", ZMsg(MSG_CHARINFO_LEVEL), ZGetMyInfo()->GetLevel(), ZMsg(MSG_CHARINFO_LEVELMARKER));
		if (pLabel) pLabel->SetText(buf);
		// XP
		pLabel = (MLabel*)pRes->FindWidget("Lobby_PlayerSpecXP");
		sprintf_safe(buf, "%s : %d%%", ZMsg(MSG_CHARINFO_XP), ZGetMyInfo()->GetLevelPercent());
		if (pLabel) pLabel->SetText(buf);
''', '')
        replace('''			pLabel = (MLabel*)pRes->FindWidget("Stage_PlayerSpecLevel");
			if (bShowMe)
				sprintf_safe(buf, "%s : %d %s", ZMsg(MSG_CHARINFO_LEVEL), ZGetMyInfo()->GetLevel(), ZMsg(MSG_CHARINFO_LEVELMARKER));
			else
				sprintf_safe(buf, "%s : %s %s", ZMsg(MSG_CHARINFO_LEVEL), pItem->GetString(1), ZMsg(MSG_CHARINFO_LEVELMARKER));
			if (pLabel) pLabel->SetText(buf);

			// XP
			pLabel = (MLabel*)pRes->FindWidget("Stage_PlayerSpecXP");
			if (bShowMe)
				sprintf_safe(buf, "%s : %d%%", ZMsg(MSG_CHARINFO_XP), ZGetMyInfo()->GetLevelPercent());
			else
				sprintf_safe(buf, "%s : -", ZMsg(MSG_CHARINFO_XP));
			if (pLabel)
			{
				pLabel->SetText(buf);
				pLabel->Enable(bShowMe);
			}
''', '')
        replace('''		sprintf_safe(szTemp, "^9%s : %d %s", ZMsg(MSG_CHARINFO_LEVEL), ZGetMyInfo()->GetLevel(), ZMsg(MSG_CHARINFO_LEVELMARKER));
		pTextArea->AddText(szTemp);
''', '', 4)
        replace('''		if (pItemDesc->m_nResLevel > ZGetMyInfo()->GetLevel())
			sprintf_safe(szBuff, "^9%s : ^1%d ^9%s", ZMsg(MSG_CHARINFO_LEVEL),
				ZGetMyInfo()->GetLevel(), ZMsg(MSG_CHARINFO_LEVELMARKER));
		else
			sprintf_safe(szBuff, "^9%s : %d %s", ZMsg(MSG_CHARINFO_LEVEL),
				ZGetMyInfo()->GetLevel(), ZMsg(MSG_CHARINFO_LEVELMARKER));
		pTextArea->AddText(szBuff);
''', '')
        # Two distinct item-description implementations, including old tooltips.
        for signature in ('bool GetItemDescStr(string& str, DWORD nItemID)',
                          'string GetRestrictionString(MMatchItemDesc* pItemDesc)'):
            start, end = block_span(text, signature)
            section = text[start:end]
            _, b = block_span(section, 'if (pItemDesc->m_nResLevel)')
            section = section[:section.index('if (pItemDesc->m_nResLevel)')] + section[b:]
            text = text[:start] + section + text[end:]
        replace('\t\tif (ZGetMyInfo()->GetLevel() < pItemDesc->m_nResLevel)\n'
            '\t\t\treturn 2;\t// Level restricted\n', '')
        for signature in ('void ZGameInterface::Sell()', 'void ZGameInterface::SellQuestItem()',
                          'void ZGameInterface::OpenSellQuestItemConfirm()'):
            body(signature, '\tShowErrorMessage(MERR_CANNOT_SELL_ITEM);')
        replace('%s(%d bounty) x %d', '%s(%d GBucks) x %d')
        replace('= %d bounty', '= %d GBucks')
    elif relative == 'Gunz/ZCharacterSelectView.cpp':
        replace('sprintf_safe( szString, "%d %s", pAccountCharInfo->nLevel, ZMsg(MSG_CHARINFO_LEVELMARKER));',
                'szString[0] = 0;\n\t\t\t\tpLabel->Show(false);')
    elif relative == 'Gunz/ZPlayerListBox.cpp':
        replace('m_Fields.Get(1)->nTabSize = 16 * fA; //level', 'm_Fields.Get(1)->nTabSize = 0; // Retained wire/list index, not a visible column.')
        replace('m_Fields.Get(2)->nTabSize = 72 * fA; //name', 'm_Fields.Get(2)->nTabSize = 88 * fA; //name')
        replace('sprintf_safe(szLevel, "%2d", nLevel);', 'szLevel[0] = 0;')
        replace('sprintf_safe(Level, "%2d", nLevel);', 'Level[0] = 0;')
    elif relative == 'Gunz/ZEquipmentListBox.h':
        replace('else if(i==2) return m_szLevel;', 'else if(i==2) return ""; // No progression column, including storage.')
    elif relative == 'Gunz/ZEquipmentListBox.cpp':
        # Header strings are legacy Korean bytes. Match the whole constructor
        # field block structurally, checking the pinned widths before replacing.
        start = text.index('\tAddField("ICON", 32);')
        end = text.index('\n\n\tm_bVisibleHeader = true;', start)
        section = text[start:end]
        if section.count('AddField(') != 4 or not all(x in section for x in (', 160);', ', 35);', ', 45);')):
            raise ValueError('Unexpected equipment columns')
        replace(section, '\tAddField("", 32);\n\tAddField("Item", 175);\n\tAddField("", 0);\n\tAddField("GBucks", 65);')
        replace('itoa_safe(nLevel, szLevel, 10);', 'szLevel[0] = 0;', 2)
    elif relative == 'Gunz/ZMyItemList.cpp':
        # An inventory price is not a resale offer; all sale paths are disabled.
        replace('pItemDesc->m_nResLevel,pItemDesc->GetBountyValue()', '0,0', 2)
    elif relative == 'Gunz/ZItemSlotView.cpp':
        replace('if (pItemDesc->m_nResLevel > nPlayerLevel) return false;', '// No character-progression equip requirement.')
    elif relative == 'Gunz/ZRoomListBox.cpp':
        remove_block('if( m_pMapInfo[i].bLimitLevel )')
    elif relative == 'Gunz/ZStageSetting.cpp':
        replace('BuildStageSettingItem("StageLevelLimit", pOutNode->nLimitLevel, StageSetting_LimitLevel);',
                'pOutNode->nLimitLevel = 0; // Rooms never restrict character progression.')
        replace('ShowStageSettingItem("StageLevelLimit", pStageSetting->nLimitLevel, StageSetting_LimitLevel);', '')
        replace('''	strcpy_safe(StageSetting_LimitLevel[0].szText, ZMsg(MSG_WORD_NONE));
	for (int i = 1; i < 4; ++i) {
		sprintf_safe(StageSetting_LimitLevel[i].szText, "%s %d", ZMsg(MSG_WORD_LEVELDIFF), i * 5);
	}
	InitStageSettingItem("StageLevelLimit", StageSetting_LimitLevel);''', '')
    elif relative == 'Gunz/ZStageInterface.cpp':
        for name in ('Stage_QuestLevel', 'Stage_QuestLevelBG'):
            replace(f'ShowWidget( "{name}", bQuestUI);', f'ShowWidget( "{name}", false);')
        replace('sprintf_safe( szText, "%s %s : %d", ZMsg( MSG_WORD_QUEST), ZMsg( MSG_CHARINFO_LEVEL), nQL);', 'szText[0] = 0;')
        replace('sprintf_safe(szText, "%s %s : %d", ZMsg(MSG_WORD_QUEST), ZMsg(MSG_CHARINFO_LEVEL), nQL);', 'szText[0] = 0;')
    elif relative == 'Gunz/ZGameClient.cpp':
        for direction in ('Up', 'Down'):
            body(f'void ZGameClient::OnGameLevel{direction}(const MUID& uidChar)',
                 '\t// Compatibility notification: no mutation, announcement, sound or effect.',
                 (f'pCharacter->Level{direction}();',))
        replace('''	blog("^9%s : %d %s", ZMsg(MSG_CHARINFO_LEVEL), pCharInfoDetail->nLevel, ZMsg(MSG_CHARINFO_LEVELMARKER));''', '')
        replace('''		wsprintf(szText,
			ZMsg(MSG_LOBBY_LIMIT_LEVEL));
		ZChatOutput(szText, ZChat::CMT_SYSTEM, ZChat::CL_LOBBY);''', '')
    elif relative == 'Gunz/ZScreenEffectManager.cpp':
        body('void ZScreenEffectManager::AddExpEffect(int nExp)',
             '\t// No experience gain/loss graphics or score-get sound.', ('PlaySoundScoreGet();',))
        body('void ZScreenEffectManager::SetGuageExpFromMyInfo()',
             '\t// Retained call boundary; there is no experience gauge.')
        replace('\t// exp\n\tcolor = D3DCOLOR_ARGB(255,200,200,200);\n\n'
                '\tDrawGuage(66.f/800.f , 70.f/600.f , min(1.f,m_fGuageEXP) * 138.f/800.f , 4.f/600.f , -1.f ,color);', '', 2)
        # The static sample level/name and empty EXP track in hp.tga.dds are
        # removed by cosmetics.py without touching HP/AP rendering or HIT.
    elif relative == 'Gunz/ZEffectManager.cpp':
        body('void ZEffectManager::AddLevelUpEffect(ZObject* pObj)',
             '\t// Retained ABI entry point; character progression has no world effect.')
    elif relative == 'MatchServer/MMatchObject.cpp':
        # Shared by server equip validation and quest rewards. Preserve missing
        # descriptor and gender checks; don't substitute a magic level of 99.
        # The pinned comment between the condition and brace is non-ASCII.
        replace('if (pItemDesc->m_nResLevel > nPlayerLevel) return false;',
                '// Compatibility argument nPlayerLevel never gates equipment.')
    elif relative == 'MatchServer/MMatchServer.cpp':
        remove_block('if (pStage->GetStageSetting()->GetLimitLevel() != 0)',
                     ('MERR_CANNOT_JOIN_STAGE_BY_LEVEL', 'nMasterLevel'))
        for bound, comparison in (('Min', '>'), ('Max', '<')):
            remove_block(f'if ((pChannel->GetLevel{bound}() > 0) &&\n'
                         f'\t\t\t(pChannel->GetLevel{bound}() {comparison} pObj->GetCharInfo()->m_nLevel))',
                         ('MERR_CANNOT_JOIN_CHANNEL_BY_LEVEL',))
        # IsNewbie is derived from legacy character progression; leaving this
        # check would still exclude internal-99 players from newcomer channels.
        remove_block('if ((pChannel->GetRuleType() == MCHANNEL_RULE_NEWBIE) && (pObj->IsNewbie() == false))',
                     ('MERR_CANNOT_JOIN_CHANNEL_BY_NEWBIE',))
        replace('''	if (!IsEquipableItem(pItem->GetDescID(), pObj->GetCharInfo()->m_nLevel, pObj->GetCharInfo()->m_nSex))
	{
		return MERR_LOW_LEVEL;
	}''', '''	if (!IsEquipableItem(pItem->GetDescID(), pObj->GetCharInfo()->m_nLevel, pObj->GetCharInfo()->m_nSex))
	{
		return MERR_CANNOT_EQUIP_ITEM; // Missing descriptor or incompatible appearance.
	}''')
    elif relative == 'MatchServer/MMatchServer_Stage.cpp':
        # Never accept an old/modified client's requested progression filter.
        # Quickjoin calls ValidateStageJoin, so it retains every non-level gate.
        replace('\tpSetting->UpdateStageSetting(pNode);',
                '\tpNode->nLimitLevel = 0; // Ignore legacy room progression filters.\n'
                '\tpSetting->UpdateStageSetting(pNode);')
        replace('pNode->nLimitLevel = pStage->GetStageSetting()->GetLimitLevel();',
                'pNode->nLimitLevel = 0; // Do not advertise a legacy progression filter.')
        remove_block('if (pNode->nLimitLevel != 0)',
                     ('MSTAGENODE_FLAG_LIMITLEVEL', 'pMaster->GetCharInfo()->m_nLevel'))
    elif relative == 'MatchServer/MMatchServer_Channel.cpp':
        replace('// Find proper channel by Level', '// Find an available channel, independent of progression')
        replace('\t\t\t\tif (pChannel->GetLevelMin() <= 0) continue;\n', '')
    elif relative == 'MatchServer/MMatchServer_Char.cpp':
        body('bool MMatchServer::CorrectEquipmentByLevel(MMatchObject* pPlayer, MMatchCharItemParts nPart, int nLegalItemLevelDiff)',
             '\treturn false; // Never unequip owned items based on legacy progression.',
             ('m_nResLevel', 'ResponseTakeoffItem('))
    elif relative == 'MatchServer/MMatchServer_Clan.cpp':
        remove_block('if (pMasterObject->GetCharInfo()->m_nLevel < CLAN_CREATING_NEED_LEVEL)',
                     ('MERR_CLAN_CREATING_LESS_LEVEL',))
    elif relative == 'MatchServer/MMatchServer_Item.cpp':
        body('bool MMatchServer::ResponseSellItem(const MUID& uidPlayer, const MUID& uidItem)', '''	// Never turn free starter/inventory equipment into GBucks.
	MMatchObject* pObj = GetObject(uidPlayer);
	if (!IsEnabledObject(pObj) || !pObj->GetCharInfo()) return false;
	MCommand* response = CreateCommand(MC_MATCH_RESPONSE_SELL_ITEM, MUID(0,0));
	response->AddParameter(new MCmdParamInt(MERR_CANNOT_SELL_ITEM));
	RouteToListener(pObj, response);
	return false;''', ('SellBountyItem(', 'm_nBP += nPrice;'))
    elif relative == 'MatchServer/MMatchServer_Quest.cpp':
        body('void MMatchServer::OnResponseSellQuestItem( const MUID& uidSender, const u32 nItemID, const int nCount )', '''	MMatchObject* player = GetObject(uidSender);
	if (!IsEnabledObject(player) || !player->GetCharInfo()) return;
	MCommand* response = CreateCommand(MC_MATCH_RESPONSE_SELL_QUEST_ITEM, MUID(0,0));
	if (!response) return;
	response->AddParameter(new MCmdParamInt(MERR_CANNOT_SELL_ITEM));
	response->AddParameter(new MCmdParamInt(player->GetCharInfo()->m_nBP));
	RouteToListener(player, response);''', ('GetBountyValue()', 'MC_MATCH_RESPONSE_SELL_QUEST_ITEM'))
    else:
        raise ValueError('Unknown progression patch: ' + relative)
    return text


FILES = [
    'Gunz/ZGameInterface.cpp', 'Gunz/ZCharacterSelectView.cpp',
    'Gunz/ZPlayerListBox.cpp', 'Gunz/ZEquipmentListBox.h', 'Gunz/ZEquipmentListBox.cpp',
    'Gunz/ZMyItemList.cpp', 'Gunz/ZItemSlotView.cpp', 'Gunz/ZRoomListBox.cpp',
    'Gunz/ZStageSetting.cpp', 'Gunz/ZStageInterface.cpp', 'Gunz/ZGameClient.cpp',
    'Gunz/ZScreenEffectManager.cpp', 'Gunz/ZEffectManager.cpp',
    'MatchServer/MMatchServer_Item.cpp', 'MatchServer/MMatchServer_Quest.cpp',
    'MatchServer/MMatchObject.cpp', 'MatchServer/MMatchServer.cpp',
    'MatchServer/MMatchServer_Stage.cpp', 'MatchServer/MMatchServer_Channel.cpp',
    'MatchServer/MMatchServer_Char.cpp', 'MatchServer/MMatchServer_Clan.cpp',
]