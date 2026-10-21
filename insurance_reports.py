"""Non-regulated technical evidence dossier for insurer / broker conversations."""
from __future__ import annotations
import io
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether,PageBreak
from reportlab.lib.enums import TA_LEFT
from .insurance_intelligence import CONTROL_CATALOG

NAVY=colors.HexColor('#0B1B2A'); TEAL=colors.HexColor('#087D78'); GRAY=colors.HexColor('#526776')
PAPER=colors.HexColor('#F1F7F7'); RED=colors.HexColor('#A74549')


def render_insurance_dossier(d):
    s=d['submission']; p=s['payload']; k=d['profile']; assessment=d.get('assessment'); reviews=s.get('reviews') or []
    output=io.BytesIO(); doc=SimpleDocTemplate(output,pagesize=(612,792),rightMargin=43,leftMargin=43,topMargin=52,bottomMargin=51,
        title='SIYAJ | Insurance Evidence Dossier',author='SIYAJ')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ArgTitleIns',fontName='Helvetica-Bold',fontSize=24,leading=30,textColor=NAVY,spaceAfter=12))
    styles.add(ParagraphStyle(name='ArgHIns',fontName='Helvetica-Bold',fontSize=12,leading=16,textColor=NAVY,spaceBefore=15,spaceAfter=7))
    styles.add(ParagraphStyle(name='ArgBodyIns',fontName='Helvetica',fontSize=8.6,leading=13.3,textColor=NAVY,spaceAfter=5))
    styles.add(ParagraphStyle(name='ArgSmallIns',fontName='Helvetica',fontSize=7.4,leading=10.5,textColor=GRAY,spaceAfter=5))
    styles.add(ParagraphStyle(name='ArgHeadCellIns',fontName='Helvetica-Bold',fontSize=7.4,leading=10,textColor=colors.white))
    styles.add(ParagraphStyle(name='ArgCellIns',fontName='Helvetica',fontSize=7.5,leading=11,textColor=NAVY))
    P=lambda value,sty='ArgBodyIns':Paragraph(escape(str(value if value is not None else 'Not provided')).replace('\n','<br/>'),styles[sty])
    story=[P('SIYAJ  /  INSURANCE INTELLIGENCE','ArgSmallIns'),Spacer(1,10),
        P('AI Agent Risk Evidence Dossier','ArgTitleIns'),
        P('Non-binding technical documentation for insurer / broker evidence discussions.','ArgBodyIns'),Spacer(1,13)]
    tab=[('Insured / organization',p.get('legal_entity')),('Engagement',s.get('project_name')),
         ('Country',s.get('region')),('Use case',p.get('use_case')),('Review owner',p.get('risk_owner')),
         ('Version',s.get('version')),('Technical assessment',s.get('assessment_id') or 'No assessment linked'),
         ('Dossier fingerprint',k.get('fingerprint_sha256'))]
    table=Table([[P(a,'ArgSmallIns'),P(b,'ArgCellIns')] for a,b in tab],colWidths=[152,373],hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PAPER),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
        ('LINEBELOW',(0,0),(-1,-2),.3,colors.HexColor('#D6E3E1'))]))
    story.extend([table,Spacer(1,15)])
    tiles=[['QUESTIONNAIRE COMPLETENESS','SELF-ATTESTED CONTROLS','EVIDENCE READINESS'],
          [str(k['questionnaire_completeness_pct'])+'%',str(k['self_attested_control_posture_pct'])+'%' if k['self_attested_control_posture_pct'] is not None else 'N/A',str(k['evidence_readiness_pct'])+'%']]
    metric=Table([[P(x,'ArgSmallIns' if i==0 else 'ArgHIns') for x in line] for i,line in enumerate(tiles)],colWidths=[175]*3)
    metric.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PAPER),('LEFTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),11),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story.extend([metric,P('Evidence status: '+k['readiness_label'],'ArgSmallIns')])
    story.append(P('Exposure context','ArgHIns'))
    for lab,key in [('Autonomy','autonomy'),('Data classification','data_classification'),('Customer impact','customer_impact'),
                    ('Agent actions','agent_actions'),('Operational volume','volume'),('Deployment','deployment'),
                    ('Data residency considerations','data_residency')]:
        story.append(P(f'{lab}: {p.get(key) or "Not supplied"}'))
    story.append(P('Priority review flags','ArgHIns'))
    for flag in (k['priority_flags'] or ['No flags in this limited dataset']): story.append(P('• '+flag))
    story.append(P('Technical assessment evidence','ArgHIns'))
    tech=k.get('observed_technical_assessment')
    if not tech:story.append(P('No technical assessment linked. No technical risk conclusion can be drawn.'))
    else:
        rows=[('Test status',tech.get('status')),('Agent mode',tech.get('agent_mode')),('Evidence classification',k.get('technical_evidence_type')),
              ('Observed exposure index',str(tech.get('observed_exposure_index'))+'/100' if tech.get('observed_exposure_index') is not None else 'Not scored'),
              ('Scored evidence coverage',str(tech.get('coverage_pct'))+'%' if tech.get('coverage_pct') is not None else 'Not scored'),
              ('Observed failed checks',tech.get('observed_failures')),('Unresolved/error checks',tech.get('unresolved_cases')),
              ('Dataset SHA-256',tech.get('dataset_fingerprint'))]
        for a,b in rows:story.append(P(str(a)+': '+str(b)))
        if k['technical_evidence_type']=='scripted_demo':story.append(P('DEMO DISCLAIMER: Scripted reference-agent results are not independently observed customer-model evidence.','ArgSmallIns'))
    story.append(P('Control questionnaire','ArgHIns'))
    tabledata=[[P('Control','ArgHeadCellIns'),P('Response','ArgHeadCellIns'),P('Verification','ArgHeadCellIns')]]
    for item in CONTROL_CATALOG:
        status=p.get('controls',{}).get(item['id'],'unknown')
        desc='Self-attested; corroborate' if status!='unknown' else 'Missing response'
        tabledata.append([P(item['name'],'ArgCellIns'),P(status.upper(),'ArgCellIns'),P(desc,'ArgCellIns')])
    t=Table(tabledata,colWidths=[229,90,206],repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PAPER]),('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.append(t)
    story.append(PageBreak())
    story.append(P('Coverage discussion topics — not recommendations','ArgHIns'))
    for line in k['coverage_discussion_lines']:
        story.append(KeepTogether([P(line['title'],'ArgBodyIns'),P(line['context'],'ArgSmallIns')]+[P('• '+q,'ArgSmallIns') for q in line['questions']]))
    story.append(P('Partner discussion / review notes','ArgHIns'))
    if not reviews:story.append(P('No partner review recorded.'))
    for row in reviews[:8]:
        story.append(KeepTogether([P(f"{row['organization']} — {row['disposition'].replace('_',' ').upper()}",'ArgBodyIns'),
            P(f"{row['reviewer']} | Version {row['version']} | {row['created_at']}",'ArgSmallIns'),P(row['notes'])]))
    story.append(P('Methodology and limitations','ArgHIns'))
    story.append(P(k['methodology'],'ArgSmallIns'))
    story.append(P(k['limitations'],'ArgSmallIns'))
    story.append(P('The dossier is neither an insurance application, quote, offer, binder or policy nor coverage advice, '
                   'and it does not purport to perform an insurer\'s underwriting function. A licensed insurer or intermediary '
                   'must independently review information and policy wording. UAE and KSA insurance-regulated services '
                   'must be authorized before they are performed.','ArgSmallIns'))
    story.append(P('References: UAE CBUAE Insurance Brokers Regulation (C 1/2024); Saudi Insurance Authority licensing; '
                  'NIST AI Risk Management Framework / Generative AI Profile.','ArgSmallIns'))
    def footer(canvas,pdf):
        canvas.setStrokeColor(colors.HexColor('#D8E6E4'));canvas.line(43,41,569,41)
        canvas.setFont('Helvetica',7);canvas.setFillColor(GRAY)
        canvas.drawString(43,29,'SIYAJ · TECHNICAL EVIDENCE ONLY · NON-BINDING')
        canvas.drawRightString(568,29,'Page '+str(pdf.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
