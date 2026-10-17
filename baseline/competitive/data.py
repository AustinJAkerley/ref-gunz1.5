"""Validated competitive item overlay; never modifies the pinned downloaded data."""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
CONFIG=json.loads((HERE/'config.json').read_text())
ITEM_NAMESPACE='http://tempuri.org/zitem.xsd'


def xp_for_max(formula):
    root=ET.parse(formula).getroot(); table=next(t for t in root if t.get('id')=='NeedExpLM')
    factors={}
    for row in table:
        for level in range(int(row.get('lower')),int(row.get('upper'))+1):factors[level]=float(row.text)
    return sum(int(level*level*factors[level]*100+.5)*2 for level in range(1,99))


def validate(data_root):
    client=ET.parse(data_root/'client/system/zitem.xml').getroot()
    server=ET.parse(data_root/'server/zitem.xml').getroot()
    ci={int(i.get('id')):i for i in client};si={int(i.get('id')):i for i in server}
    for item in [CONFIG['primary'],CONFIG['secondary'],*CONFIG['revolvers'],*CONFIG['male_set'],*CONFIG['female_set'],*CONFIG['male_alternate'],*CONFIG['female_alternate']]:
        if ci[item].attrib!=si[item].attrib:raise ValueError(f'Client/server item mismatch: {item}')
        if 'admin' in ci[item].get('name','').lower():raise ValueError('Admin gear forbidden')
    for item in (CONFIG['primary'],CONFIG['secondary']):
        if ci[item].get('weapon')!='shotgun':raise ValueError('Shotgun required')
    for item in CONFIG['revolvers']:
        if ci[item].get('weapon')!='revolverx2' or int(ci[item].get('damage','0'))<=0:raise ValueError('Real revolvers required')
    for key,weapon,world_id,kind in (('hp_pack','medkit',130,'hp'),('armor_pack','repairkit',131,'ap')):
        item=CONFIG[key]
        if ci[item].attrib!=si[item].attrib or ci[item].get('weapon')!=weapon:raise ValueError('Pack definition mismatch')
        for path in (data_root/'client/system/worlditem.xml',data_root/'server/worlditem.xml'):
            entries={int(e.get('id')):e for e in ET.parse(path).getroot().iter('WORLDITEM')}
            if entries[world_id].findtext('TYPE')!=kind:raise ValueError('Wrong pack pickup type')
    for sex in ('male','female'):
        for key in (sex+'_set',sex+'_alternate'):
            for item,slot in zip(CONFIG[key],('head','chest','hands','legs','feet')):
                if ci[item].get('slot')!=slot or ci[item].get('res_sex')!=('m' if sex=='male' else 'f'):raise ValueError('Outfit slot/sex mismatch')
    return ci


def header(data_root):
    validate(data_root)
    def array(name,values):return 'constexpr int '+name+'[]={'+','.join(map(str,values))+'};\n'
    output='#pragma once\nnamespace competitive {\nconstexpr int maxLevelXP='+str(xp_for_max(data_root/'server/formula.xml'))+';\n'
    for sex in ('male','female'):
        equip=CONFIG[sex+'_set']+CONFIG['rings']+[2,CONFIG['primary'],CONFIG['secondary'],CONFIG['hp_pack'],CONFIG['armor_pack']]
        output+=array(sex+'Equipment',equip)+array(sex+'Alternate',CONFIG[sex+'_alternate'])
    return output+array('revolvers',CONFIG['revolvers'])+'}\n'


def install_items(data_root,runtime):
    validate(data_root)
    # MXmlDocument looks up literal "xml" / "ITEM" names, not XML namespaces.
    # Preserve the original default namespace; ElementTree's ns0: prefix makes
    # both the real client and server reject the entire descriptor file.
    ET.register_namespace('',ITEM_NAMESPACE)
    # Explicit basic ring requested by user, not the pack's 1000 HP/AP admin ring.
    for relative in ('client/system/zitem.xml','server/zitem.xml'):
        source=data_root/relative;target=runtime/relative
        tree=ET.parse(source);root=tree.getroot();ids={int(e.get('id')) for e in root}
        if root.tag!='{'+ITEM_NAMESPACE+'}XML':raise ValueError('Unexpected item XML namespace/root')
        for item,name,hp,ap,weight,level in ((25011,'Basic Ring',10,10,0,0),):
            if item in ids:raise ValueError('Ring overlay ID already in source; review before replacing')
            ET.SubElement(root,'{'+ITEM_NAMESPACE+'}ITEM',{'id':str(item),'name':name,'type':'equip','slot':'finger','res_sex':'a',
                'res_level':str(level),'weight':str(weight),'bt_price':'0','hp':str(hp),'ap':str(ap),'maxwt':'0',
                'sf':'0','fr':'0','cr':'0','pr':'0','lr':'0','color':'#FFFFFFFF','desc':'Competitive starter ring'})
        target.parent.mkdir(parents=True,exist_ok=True)
        tree.write(target,encoding='utf-8',xml_declaration=True)
    for relative in ('client/system/worlditem.xml','server/worlditem.xml'):
        tree=ET.parse(data_root/relative)
        entries={int(e.get('id')):e for e in tree.getroot().iter('WORLDITEM')}
        for item in (130,131):entries[item].find('AMOUNT').text='20'
        tree.write(runtime/relative,encoding='utf-8',xml_declaration=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--header',type=Path);p.add_argument('--runtime',type=Path);a=p.parse_args()
    if a.header:a.header.write_text(header(a.data))
    if a.runtime:install_items(a.data,a.runtime)