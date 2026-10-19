import json,glob,os,sys,csv
bp=sys.argv[1]; locf=sys.argv[2]
loc={}
with open(locf,encoding='utf-8-sig') as fh:
    for row in csv.reader(fh):
        if len(row)>=2: loc[row[0]]=row[1]
def L(f): return json.load(open(f,encoding='utf-8-sig'))
def cost(c): return ' '.join(f"{x['Amount']}{x['Id']}" for x in c)
out=[]
out.append('# BUILDINGS: name | faction | cost | science | workers | details')
for f in sorted(glob.glob(os.path.join(bp,'Buildings','**','*.json'),recursive=True)):
    d=L(f); b=d.get('BuildingSpec')
    if not b: continue
    tn=d['TemplateSpec']['TemplateName']
    lab=d.get('LabeledEntitySpec',{}); dn=loc.get(lab.get('DisplayNameLocKey',''),tn)
    det=[]
    w=d.get('WorkplaceSpec')
    ws=f"{w['MaxWorkers']}" if w else '-'
    if w and w.get('WorkerTypeUnlockCosts'): ws+=' (bot:'+','.join(str(x['ScienceCost']) for x in w['WorkerTypeUnlockCosts'])+'sp)'
    if 'ManufactorySpec' in d: det.append('recipes='+','.join(d['ManufactorySpec']['ProductionRecipeIds']))
    if 'DwellingSpec' in d: det.append(f"beds={d['DwellingSpec']['MaxBeavers']}")
    if 'StockpileSpec' in d: det.append(f"cap={d['StockpileSpec']['MaxCapacity']} {d['StockpileSpec']['WhitelistedGoodType']}")
    if 'SimpleOutputInventorySpec' in d: det.append(f"outinv={d['SimpleOutputInventorySpec']['Capacity']}")
    m=d.get('MechanicalNodeSpec')
    if m and (m.get('PowerInput') or m.get('PowerOutput')): det.append(f"power in={m.get('PowerInput')} out={m.get('PowerOutput')}")
    for k in ('WaterInputPipeSpec',):
        if k in d: det.append(f"pipeMaxDepth={d[k].get('MaxDepth')}")
    for k in ('WaterMoverSpec','FloodgateSpec','RangedEffectBuildingSpec','BreedingPodSpec','DynamiteSpec','DrillSpec','WaterSourceRegulatorSpec','FillValveSpec','ThrottlingValveSpec','GravityBatterySpec','WaterPoweredGeneratorSpec','WindPoweredGeneratorSpec','WalkerPoweredGeneratorSpec','GoodPoweredGeneratorSpec','UndergroundWaterSourceDrillSpec','AreaNeedApplierSpec','DistrictCenterSpec','LumberjackFlagSpec','GathererFlagSpec','ForesterSpec','PlanterBuildingSpec','ScavengerSpec','HaulingCenterSpec','WonderSpec','GoodConsumingBuildingSpec','ProductionIncreaserSpec','ContinuousEffectBuildingSpec','AttractionSpec','GoodConsumingAttractionSpec','MovementSpeedBoostingBuildingSpec','BuilderHubSpec','WorkplaceBonusesSpec','BlockObjectWithPathRangeSpec','TunnelSpec','WaterOutputSpec','ManufactoryWaterContaminationProducerSpec','HiveSpec','ContaminationSensorSpec','DepthSensorSpec','FlowSensorSpec','WaterObstacleSpec','GroundRaiserSpec','SoilBarrierSpec','WorkshopRandomNeedApplierSpec','ProcreationHouseSpec','RestPlaceSpec','PoweredGoodConsumingBuildingSpec','ManufactoryWaterProducerSpec'):
        if k in d: det.append(k.replace('Spec','')+'='+json.dumps(d[k],separators=(',',':'))[:300])
    fac='FT' if 'Folktails' in tn else ('IT' if 'IronTeeth' in tn else 'both')
    out.append(f"{dn} [{tn}] | {fac} | {cost(b['BuildingCost'])} | {b['ScienceCost']} | {ws} | {'; '.join(det)}")
out.append('\n# RECIPES: id | hours/cycle | in -> out | science | fuel')
for f in sorted(glob.glob(os.path.join(bp,'Recipes','*.json'))):
    r=L(f)['RecipeSpec']
    out.append(f"{r['Id']} | {r['CycleDurationInHours']}h | {cost(r['Ingredients'])} -> {cost(r['Products'])} | sp={r['ProducedSciencePoints']} | fuel={r['Fuel']} x{r['CyclesFuelLasts']}")
out.append('\n# NATURAL RESOURCES')
for f in sorted(glob.glob(os.path.join(bp,'NaturalResources','**','*.json'),recursive=True)):
    d=L(f); n=os.path.basename(f).split('.')[0]
    s=[]
    for k in ('GrowableSpec','PlantableSpec','CuttableSpec','GatherableSpec','WateredNaturalResourceSpec','FloodableNaturalResourceSpec','ReproducibleSpec'):
        if k in d: s.append(k.replace('Spec','')+'='+json.dumps(d[k],separators=(',',':')))
    out.append(n+' | '+' ; '.join(s))
out.append('\n# NEEDS: id | group | char | dailyDelta | min/max | favorable/unfavorable wellbeing')
for f in sorted(glob.glob(os.path.join(bp,'Needs','*.json'))):
    n=L(f)['NeedSpec']
    out.append(f"{n['Id']} | {n['NeedGroupId']} | {n['CharacterType']} | {n['DailyDelta']} | {n['MinimumValue']}/{n['MaximumValue']} | +{n['FavorableWellbeing']}/{n['UnfavorableWellbeing']}")
out.append('\n# NEED COLLECTIONS')
for f in sorted(glob.glob(os.path.join(bp,'NeedCollections','*.json'))):
    out.append(os.path.basename(f)+' '+json.dumps(L(f),separators=(',',':'))[:1500])
out.append('\n# GOODS consumption effects')
for f in sorted(glob.glob(os.path.join(bp,'Goods','*.json'))):
    g=L(f)['GoodSpec']
    if g.get('ConsumptionEffects'): out.append(f"{g['Id']} | {g['ConsumptionEffects']} | weight={g['Weight']}")
out.append('\n# WELLBEING TIERS')
for f in sorted(glob.glob(os.path.join(bp,'WellbeingTiers','*.json'))):
    w=L(f)['WellbeingTierSpec']; out.append(f"{w['CharacterType']} {w['BonusId']}: "+' '.join(f"{b['Wellbeing']}:{b['Multiplier']}" for b in w['Bonuses']))
out.append('\n# CHARACTERS')
for f in sorted(glob.glob(os.path.join(bp,'Characters','**','*.json'),recursive=True)):
    d=L(f); out.append(os.path.basename(f)+' '+json.dumps({k:v for k,v in d.items() if any(x in k for x in ('Life','Child','Age','Need','Carr','Walk','Speed','Bot','Grow','Work','Mortal','Procre'))},separators=(',',':'))[:1500])
open(sys.argv[3],'w',encoding='utf-8').write('\n'.join(out))
