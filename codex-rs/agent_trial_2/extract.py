from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
OUT=Path('/home/surui-wsl/code/codex/codex-rs/agent_trial_2')
SRC=Path('/home/surui-wsl/code/codex/parsed data/quotes_pdf_ids.xlsx')
start=datetime.now(timezone.utc).isoformat()
source_hash=hashlib.sha256(SRC.read_bytes()).hexdigest()
w=openpyxl.load_workbook(SRC,data_only=False); source=list(w.active.iter_rows(min_row=2,max_row=51,values_only=True))
aa={'R':'Arg','E':'Glu','S':'Ser','W':'Trp','K':'Lys','H':'His','N':'Asn','D':'Asp','Q':'Gln','A':'Ala','L':'Leu','M':'Met'}
data={}
def add(i,mut,mech,reason): data.setdefault(i,[]).append((mut,mech,reason))
def none(i,mech,reason): add(i,'None specified — residue interaction only',mech,reason)
def partial(i,protein,residues,mech,reason):
 for r in residues: add(i,f'{protein} {r} → replacement Not stated',mech,reason+' The replacement amino acid is absent; no complete substitution can be decoded.')
none(6,'Unspecified','hGH Arg64 contacts receptor Asp164 and Glu44; interaction chemistry is not stated.')
for i in [7,10,42,44,45,47,48,49]:
 for r in ['R64','R167','R178','E65','E174']:
  add(i,f'Hormone (specific identity Not stated) {r}A — {aa[r[0]]}{r[1:]} → Ala','Electrostatic','Authors propose electrostatic guidance of hormone to receptor. Arg-to-Ala substitutions are reported as producing the largest on-rate reductions (~2-fold); Glu-to-Ala substitutions produce the largest increases (nearly 2-fold). These are grouped observations, not precise individual measurements. Listed as separate substitutions; the quote does not explicitly establish single-mutant versus combined-construct testing. Specific hormone identity is not supplied.')
none(12,'Packing','Aliphatic portion of hGH Arg64 packs against Trp169; guanido group interacts with hGHbp Asp164 and Glu44, without a stated interaction type for those contacts. No substitution stated.')
none(13,'Unspecified','hGH Arg64 contacts receptor Asp164 and Glu44; no interaction chemistry specified.')
none(16,'Saltbridge','Explicit salt bridge between receptor linker Glu127 and hGH Lys41.')
none(25,'Hydrophobic','Ile103, Ile105, Pro106 and Ile165 join tryptophans in a hydrophobic patch; contributions reported collectively as 1.5–3.5 kcal/mol. No substitutions or protein identity supplied.')
none(29,'Hydrogenbonding','Explicit hydrogen bond between Lys167 carbonyl oxygen and hGH Asn68 Ne2; protein carrying Lys167 not stated.')
none(33,'Unspecified','Receptor Arg217/Asn218 cluster with hGH His18/His21/Glu174. Quote explicitly reports no intermolecular hydrogen bonds here; generic contact does not define a positive interaction mechanism.')
for i in [52,54,56]: none(i,'Hydrogenbonding','Arg43 hydrogen-bonds to hGH Asp171 and Thr175; protein carrying Arg43 not named.')
for i in [53,55,57]:
 for replacement,effect in [('Leu','0.5'),('Met','1'),('Ala',None)]:
  add(i,f'Protein Not stated; Arg43 → {replacement}','Packing',f'Quote attributes most energetic contribution of the alanine substitution to intramolecular interactions of Arg43 alkyl portion, including van der Waals packing beneath Trp169. Leu/Met substitutions remove polar interactions while intended to maintain packing. '+(f'Arg43→{replacement} destabilizes complex by {effect} kcal/mol. ' if effect else 'Alanine substitution is explicitly mentioned for Arg43 in context; its exact destabilization is not given. ')+'This is the authors’ interpretation; electrostatic interactions with hGH are described as relatively unimportant for affinity. Figures 3 and 6; Table 2.')
none(58,'Saltbridge','Arg71 forms a salt bridge to hGH Glu56. Reported burial is 80 AÊ 2; OCR unit retained in quote and not silently repaired. Protein carrying Arg71 not named.')
add(65,'Protein Not stated; S219A — Ser219 → Ala','Unspecified','Affinity is essentially unchanged relative to wild type. No causal interaction is given; quote contains OCR artifacts.')
none(75,'Hydrogenbonding','Ang Arg5/Gln12 make water-mediated hydrogen bonds with hRI Ile436/Asp435 respectively. Additional Ang–Asp435 van der Waals contact has unspecified Ang residue.')
none(76,'Hydrogenbonding','Explicit direct Trp89–Glu344 hydrogen bond and water-mediated bonds: Ang Gly86 to RI Glu206/Trp263, Ang Trp89 to RI Glu344.')
none(77,'Unspecified','Ang Trp89 interacts with Glu344/Glu401 and two unnamed RI residues; chemistry not stated and antecedent unresolved.')
add(78,'Ang E108A — Glu108 → Ala','Unspecified','Explicit Glu108→Ala substitution has no adverse effect; endpoint is not specified in this excerpt. Nearby contacts are described as weak but no chemistry or causal mechanism for E108A is established. Chen and Shapiro, 1997 is cited within quote.')
partial(78,'Protein Not stated',['His114','Tyr437'],'Unspecified','Mutations are mentioned as having similar consequences; additional Tyr contacts with Ang Glu67/Ala106/Glu108 are suggested to be weak, and Glu67 partially disordered.')
partial(79,'Ang',['His8','Arg32','His114'],'Unspecified','These substitutions have reported G values >0.5 kcal/mol; quote states none of the other Ang mutations reduce binding energy by >1 kcal/mol. No interaction mechanism supplied; G notation may be incomplete.')
for i in [80,87]: partial(i,'Ang',['His13','Arg31','Arg33','Lys50','Lys60','Arg66','Asn68','Arg70','Glu108'],'Unspecified','Modifications have no significant effect on RI binding affinity. Modification type and causal mechanism are not stated.')
for i in [81,97]:
 partial(i,'hRI',['Trp261','Lys320'],'VanderWaals','Substitutions barely change affinity; residues are explicitly described as making only van der Waals contacts and small nonpolar ASA changes.')
 partial(i,'Ang',['His84','Glu108'],'VanderWaals','Substitutions barely change affinity; residues are explicitly described as making only van der Waals contacts and small nonpolar ASA changes.')
add(82,'RI des(460) — deletion of Ser460','Hydrogenbonding','des(460) derivative increases Ki 8.5-fold. Quote attributes this largely to removal of Ser460 interaction with His8 rather than Gln12; these are explicitly identified as hydrogen-bonding partners. Deletion interpretation follows des(460) notation and stated removal; numbering not independently verified.')
for r,e in [('His8','4.6'),('Gln12','1.6')]: add(82,f'Ang {r} → Ala','Hydrogenbonding',f'Individually substituting His8 and Gln12 by Ala gives respective 4.6- and 1.6-fold changes in the Ki discussion; {r} corresponds to {e}-fold. Authors use this to assign RI Ser460 interaction primarily to His8. No independent structural assignment.')
none(83,'Unspecified','Contact pairs explicitly listed for Ang–RI; no substitutions or interaction chemistry stated. Wording “contacts rate involve” is retained.')
add(84,'Ang R5A — Arg5 → Ala','Unspecified','Interleaved/OCR-corrupted text explicitly says mutation of Ang Arg5 to Ala, but its outcome is truncated at “increased”. Asp41–RI Lys320 hydrogen bond belongs to different residues and cannot establish R5A mechanism. No restoration of missing text attempted.')
none(85,'Hydrogenbonding','Lys40 forms two hydrogen bonds to RI Asp435; its alkyl portion also makes van der Waals contacts with Tyr434. Quote names hRI–Ang complex; no mutation is specified. OCR ?-amino group retained.')
add(86,'Ang K40Q — Lys40 → Gln','Saltbridge','Binding weakens 1300-fold. Quote first describes proposed hydrogen bonding, then states structure reveals two salt bridges between Lys40 and RI Asp435. No PDB accession is given. Lee and Vallee, 1989; Chen and Shapiro, 1997; Table IV/Figure 5A.')
add(86,'RI D435A — Asp435 → Ala','Saltbridge','Substitution decreases affinity almost as much as Ang K40Q; exact individual fold decrease not stated. Structure is said to reveal Lys40–Asp435 salt bridges. Chen and Shapiro, 1997; Table IV/Figure 5A.')
add(86,'Joint complex: Ang K40Q (Lys40 → Gln) + RI D435A (Asp435 → Ala)','Saltbridge','Combined mutant complex dissociates at same rate as K40Q Ang with native RI. This jointly measured kinetic result is retained on the combined-complex entry and is not converted into affinity. Quote states Lys40–Asp435 salt bridges; Chen and Shapiro, 1997.')
for i in [88,92]: none(i,'Hydrogenbonding','Ang Arg5/Gln12 form water-mediated hydrogen bonds to hRI Ile436/Asp435 respectively; no substitution stated.')
none(89,'Hydrogenbonding','Gln12 and His8 hydrogen-bond to hRI Ser460. Gln12 placement in P1 site is an expectation; no mutation stated.')
for i in [90,91]: none(i,'Hydrogenbonding','Ang Arg31–RI Asp35 and Ang Arg32–RI Asp36 make hydrogen bonds and van der Waals interactions. No substitution; ?-helix OCR artifact retained. Figure 5E.')
none(93,'Hydrogenbonding','Arg5 forms two hydrogen bonds to Trp438 carbonyl and van der Waals contacts to Ser439/Glu440; protein identity is not stated explicitly in this quote. Figure 5B.')
none(94,'Hydrogenbonding','Quote explains an unspecified change by loss of RI C-terminal interactions and describes Arg5–RI Trp438 hydrogen bonds. Antecedent and substitution are absent; no mutation inferred.')
add(95,'Ang R5A — Arg5 → Ala','Unspecified','Dissociation constant increases 50-fold. This is an equilibrium constant, not a dissociation rate. Quote gives no causal mechanism. Shapiro and Vallee, 1992.')
none(96,'Hydrogenbonding','Direct hydrogen bonds join hRI Ser289–Ang Gly86 and hRI Glu344–Ang Trp89; no mutation stated.')
none(98,'Hydrogenbonding','Direct hydrogen bonds join hRI Ser289–Ang Gly86 and Glu344–Trp89; water-mediated bonds join hRI Trp263–Ang Gly86 and Glu344–Ang Trp89. No mutation stated.')
none(99,'Complementarity','Shape complementarity is explicitly high in specified hRI–Ang interface regions; no substitution specified. This describes the interface, not a measured mutation mechanism.')
partial(100,'hRI',['Trp263','Trp318','Trp375'],'Hydrophobic','Replacements give grouped G values of 1.0–1.5 kcal/mol; residues undergo grouped 34–60 AÊ 2 reductions in hydrophobic ASA upon binding. Authors link mutational observations to hydrophobic burial; exact per-residue values and replacement identities are not given. OCR retained.')
none(101,'VanderWaals','Trp318/Trp375 envelop Ang Pro88 with 15 total van der Waals contacts. Protein carrying the tryptophans not named; no mutation specified.')
assert len(source)==50 and set(data)=={r[0] for r in source}
headers=['PDB','Mutation DECODED','Mechanism','Citation','Quote','Reason']
book=openpyxl.Workbook(); results=book.active; results.title='Results'; results.append(headers)
summary=book.create_sheet('Source summary'); summary.append(['Source index','Excel row','ID','Source citation label','Quote','Result rows','Entry count','PDB status'])
evidence=book.create_sheet('Evidence'); eh=['Source index','Excel row','ID','Result row','Evidence scope','Mutation evidence','Mechanism','Observed effects and limitations']; evidence.append(eh)
ev=[]
for n,(i,c,q) in enumerate(source,1):
 first=results.max_row+1
 for mut,mech,reason in data[i]:
  row=results.max_row+1
  results.append(['Not stated',mut,mech,f'Supplied quote only; source label: {c}; source Excel row {n+1}, ID {i}',q,reason+' PDB identifier not stated in quote; citation filename was not used as structural or protein evidence.'])
  er=[n,n+1,i,row,'Only this source row quote; no external verification',mut,mech,reason]; evidence.append(er); ev.append(er)
 summary.append([n,n+1,i,c,q,', '.join(map(str,range(first,results.max_row+1))),len(data[i]),'Not stated in quote'])
activity=book.create_sheet('Activity'); ah=['Recorded UTC','Action','Details','Token usage']; activity.append(ah)
logs=[ [start,'Background/setup','Read applicable quote-to-pdb-mutation SKILL.md and inspected first 50 data rows using openpyxl. Skill instructions overridden by quote-only evidence and one-word mechanisms. Setup occurred before this timestamp; no invented timing.','Not measured'],[start,'Independent extraction','Authored interpretations from each quote only. No web, PDFs, previous extraction code/results, other-agent outputs, or cross-row scientific enrichment. Repeated quotes retain separate source records.','Not measured'],[start,'Limitations','All PDB values Not stated. Protein abbreviations preserved without unsupported expansions. Incomplete substitutions retain unknown targets. Grouped on-rate excerpt does not explicitly resolve construct design; separate listed substitutions retain caveat. Mechanism labels encode interactions stated in quote, with observed effects in Reason. No primary-source verification.','Not measured']]
for s in book:
 s.freeze_panes='A2'; s.auto_filter.ref=s.dimensions
 for cell in s[1]: cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill('solid',fgColor='24476B')
 for row in s:
  for cell in row:
   if isinstance(cell.value,str): cell.data_type='s'
   cell.alignment=Alignment(wrap_text=True,vertical='top')
 for col in range(1,s.max_column+1): s.column_dimensions[get_column_letter(col)].width=24 if col<5 else 70
results.column_dimensions['B'].width=60; results.column_dimensions['D'].width=65
path=OUT/'results.xlsx'
logs.append([datetime.now(timezone.utc).isoformat(),'Validation','Verified 50-row source coverage and exact quote preservation in memory; all mechanism labels are single words; all cell text stored literally. Source SHA256 '+source_hash,'Not measured'])
for r in logs: activity.append(r)
book.save(path)
check=openpyxl.load_workbook(path,data_only=False)
assert check['Source summary'].max_row==51
for n,(_,_,quote) in enumerate(source,2): assert check['Source summary'].cell(n,5).value==quote
for n,(_,_,quote) in enumerate(source,2):
 for row in map(int,check['Source summary'].cell(n,6).value.split(', ')): assert check['Results'].cell(row,5).value==quote
assert all(len(r[2].value.split())==1 for r in check['Results'].iter_rows(min_row=2))
assert not any(c.data_type=='f' for s in check for row in s for c in row)
assert hashlib.sha256(SRC.read_bytes()).hexdigest()==source_hash
for filename,head,rows in [('evidence_log.csv',eh,ev),('activity_log.csv',ah,logs)]:
 with (OUT/filename).open('w',newline='',encoding='utf-8-sig') as f: cw=csv.writer(f);cw.writerow(head);cw.writerows(rows)
report={'source_rows':50,'expanded_result_entries':results.max_row-1,'evidence_rows':len(ev),'source_unchanged':True,'quote_preservation':'passed','one_word_mechanisms':'passed','no_formulas':'passed','tokens':'Not measured','source_sha256':source_hash}
(OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
