_g='splitByVisits'
_f='processing-options'
_e='alerts'
_d='unique_venues'
_c='total_checkins'
_b='fileInput'
_a='loading'
_Z='results'
_Y='duplicates'
_X='Total Venue Checkins'
_W='utf-8'
_V='last_checkin'
_U='first_checkin'
_T='total_venue_checkins'
_S='venue_lng'
_R='venue_lat'
_Q='venue_name'
_P='text/csv'
_O='dragover'
_N='success'
_M='error'
_L='info'
_K='5+_visits'
_J='2-4_visits'
_I='1_visit'
_H='venue'
_G='block'
_F=True
_E='created_at'
_D='active'
_C='none'
_B='uploadArea'
_A=None
import csv,json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any,Dict,List,Optional,Union
@dataclass
class VenueLocation:
	name:str;latitude:float;longitude:float
	def __hash__(A):return hash((A.name,A.latitude,A.longitude))
class UntappdParser:
	desired_keys={'beer_name','brewery_name','beer_type',_Q,_R,_S,_E,_T,_U,_V}
	def __init__(A,data=_A,filename=_A):
		B=filename
		if data is not _A:A.data=data
		elif B is not _A:A.filename=Path(B);A.data=A._load_data()
		else:raise ValueError('Either data or filename must be provided')
	def _load_data(A):
		with open(A.filename,'r',encoding=_W)as B:return json.load(B)
	def get_unique_entries(B,key):
		A=key
		if A==_H:return B._get_unique_venues()
		return list({B[A]:B for B in B.data if B.get(A)is not _A}.values())
	def _get_unique_venues(I):
		E=defaultdict(int);F={};G=defaultdict(list)
		for A in I.data:
			B=VenueLocation(name=A[_Q],latitude=A[_R],longitude=A[_S]);E[B]+=1;F[B]=A
			if _E in A:G[B].append(A[_E])
		H=[]
		for(B,A)in F.items():
			D=A.copy();D[_T]=E[B];C=G[B]
			if C:C.sort();D[_U]=C[0];D[_V]=C[-1]if len(C)>1 else _A
			H.append(D)
		return H
	def clean_data(B,data,strip_backend=_F,fancy_dates=_F,human_keys=_F):
		A=data.copy()
		if strip_backend:A=B._strip_backend_keys(A)
		if fancy_dates:A=B._format_dates(A)
		if human_keys:A=B._humanize_keys(A)
		return A
	def _strip_backend_keys(B,data):
		A=data
		if not A:return A
		C=set(A[0].keys())-B.desired_keys;return[{A:B for(A,B)in A.items()if A not in C}for A in A]
	@staticmethod
	def _format_dates(data):
		def B(date_str):return datetime.strptime(date_str,'%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y at %I:%M%p')
		for A in data:
			A.pop(_E,_A)
			if(C:=A.pop(_U,_A)):A['First Check-in']=B(C)
			if(D:=A.pop(_V,_A)):A['Last Check-in']=B(D)
		return data
	@staticmethod
	def _humanize_keys(data):return[{A.replace('_',' ').title():B for(A,B)in A.items()}for A in data]
	def get_visit_distribution(F,data):
		C=[];D=[];E=[]
		for A in data:
			B=A.get(_X,A.get(_T,0))
			if B==1:C.append(A)
			elif 2<=B<=4:D.append(A)
			elif B>=5:E.append(A)
		return{_I:C,_J:D,_K:E}
	def save_files(C,data,base_filename,split_by_visits=False):
		B=data;A=base_filename
		with open(f"{A}.json",'w',encoding=_W)as D:json.dump(B,D,indent=2,ensure_ascii=False)
		if split_by_visits and _H in A:C._save_visit_distribution_csvs(B,A)
		else:C._save_csv(B,f"{A}.csv")
	def _save_csv(E,data,filename):
		A=data
		if not A:return
		C=list(A[0].keys())
		with open(filename,'w',newline='',encoding=_W)as D:B=csv.DictWriter(D,fieldnames=C);B.writeheader();B.writerows(A)
	def _save_visit_distribution_csvs(D,data,base_filename):
		A=base_filename;B=D.get_visit_distribution(data);F=[(B[_I],f"{A}_1_visit.csv",'1 visit'),(B[_J],f"{A}_2-4_visits.csv",'2-4 visits'),(B[_K],f"{A}_5+_visits.csv",'5+ visits')]
		for(C,E,G)in F:
			if C:D._save_csv(C,E);print(f"  - {G}: {len(C)} venues saved to {E}")
	def get_stats(A):B=A.get_unique_entries(_H);return{_c:len(A.data),_d:len(B),_Y:len(A.data)-len(B)}
import csv,html,io,json
from js import URL,Blob,FileReader,console,document,window
from pyodide.ffi import create_proxy
class AppState:
	def __init__(A):A.parser=_A;A.processed_venues=_A;A.cleaned_data=_A
	def reset(A):A.parser=_A;A.processed_venues=_A;A.cleaned_data=_A
	def has_data(A):return A.cleaned_data is not _A
app_state=AppState()
def show_alert(message,alert_type=_L):A=document.getElementById(_e);A.innerHTML=f'<div class="alert alert-{alert_type}">{message}</div>';window.setTimeout(lambda:setattr(A,'innerHTML',''),5000)
def escape_html(text):
	if text is _A:return''
	return html.escape(str(text),quote=_F)
def data_to_csv(data):
	A=data
	if not A:return''
	try:B=io.StringIO();D=list(A[0].keys())if A else[];C=csv.DictWriter(B,fieldnames=D);C.writeheader();C.writerows(A);return B.getvalue()
	except Exception as E:console.error(f"CSV generation error: {str(E)}");show_alert('Error generating CSV file',_M);return''
def download_file(content,filename,mime_type='text/plain'):C=Blob.new([content],{'type':mime_type});B=URL.createObjectURL(C);A=document.createElement('a');A.href=B;A.download=filename;A.click();URL.revokeObjectURL(B)
def process_file(file_content):
	try:
		A=json.loads(file_content)
		if not isinstance(A,list):raise ValueError('Data must be an array of check-ins')
		if len(A)==0:raise ValueError('No check-ins found in file')
		D=[_Q,_R,_S,_E];E=A[0];B=[A for A in D if A not in E]
		if B:raise ValueError(f"Missing required fields: {", ".join(B)}")
		F=document.getElementById('humanKeys').checked;G=document.getElementById('stripBackend').checked;H=document.getElementById('fancyDates').checked;app_state.parser=UntappdParser(data=A);app_state.processed_venues=app_state.parser.get_unique_entries(_H);app_state.cleaned_data=app_state.parser.clean_data(app_state.processed_venues,strip_backend=G,fancy_dates=H,human_keys=F);update_results();document.getElementById(_B).style.display=_C;document.getElementById(_f).style.display=_C;document.getElementById(_Z).classList.add(_D);document.getElementById(_a).classList.remove(_D);show_alert(f"Successfully processed {len(A)} check-ins!",_N)
	except Exception as C:app_state.reset();document.getElementById(_a).classList.remove(_D);show_alert(f"Error: {str(C)}",_M);console.error(f"Processing error: {str(C)}")
def update_results():
	H='fivePlus';G='twoToFour';F='singleVisit'
	if not app_state.has_data():return
	B=app_state.parser.get_stats();document.getElementById('totalCheckins').textContent=f"{B[_c]:,}";document.getElementById('uniqueVenues').textContent=f"{B[_d]:,}";document.getElementById(_Y).textContent=f"{B[_Y]:,}";N=document.getElementById(_g).checked;I=document.getElementById('split-buttons')
	if N:I.style.display='contents';C=app_state.parser.get_visit_distribution(app_state.cleaned_data);document.getElementById(F).textContent=f"{len(C[_I]):,}";document.getElementById(G).textContent=f"{len(C[_J]):,}";document.getElementById(H).textContent=f"{len(C[_K]):,}";document.getElementById(F).parentElement.parentElement.style.display=_G;document.getElementById(G).parentElement.parentElement.style.display=_G;document.getElementById(H).parentElement.parentElement.style.display=_G
	else:I.style.display=_C;document.getElementById(F).parentElement.parentElement.style.display=_C;document.getElementById(G).parentElement.parentElement.style.display=_C;document.getElementById(H).parentElement.parentElement.style.display=_C
	O=sorted(app_state.cleaned_data,key=lambda x:x.get(_X,0),reverse=_F);P=O[:10];J=''
	for A in P:
		D=A.get(_X,0);Q='badge-primary'if D==1 else'badge-warning'if D<=4 else'badge-success';R=escape_html(A.get('Venue Name','(No venue)'));K=A.get('Venue Lat');L=A.get('Venue Lng')
		if K is not _A and L is not _A:
			try:E=f"{float(K):.4f}, {float(L):.4f}"
			except(ValueError,TypeError):E='Invalid coordinates'
		else:E='No location'
		S=escape_html(A.get('First Check-In','N/A'));M=escape_html(A.get('Last Check-In',''));J+=f'''
        <div class="venue-item">
            <div class="venue-name">
                {R}
                <span class="badge {Q}">{D} visits</span>
            </div>
            <div class="venue-details">
                📍 {E}<br>
                🗓️ First: {S}
                {f"<br>🗓️ Last: {M}"if M else""}
            </div>
        </div>
        '''
	document.getElementById('venuePreview').innerHTML=J
def handle_file(event):
	B=event.target.files
	if B.length>0:
		A=B.item(0)
		if not A.name.endswith('.json'):show_alert('Please upload a JSON file',_M);return
		if A.size>52428800:show_alert('File size exceeds 50MB limit',_M);return
		document.getElementById(_a).classList.add(_D);document.getElementById(_Z).classList.remove(_D);C=FileReader.new()
		def D(e):process_file(e.target.result)
		C.onload=create_proxy(D);C.readAsText(A)
def dragover(e):e.preventDefault();document.getElementById(_B).classList.add(_O)
def dragleave(e):e.preventDefault();document.getElementById(_B).classList.remove(_O)
def drop(e):
	e.preventDefault();document.getElementById(_B).classList.remove(_O);A=e.dataTransfer.files
	if A.length>0:document.getElementById(_b).files=A;handle_file(e)
def export_all(event):
	if app_state.has_data():A=json.dumps(app_state.cleaned_data,indent=2);download_file(A,'venues_all.json','application/json')
def export_all_csv(event):
	if app_state.has_data():A=data_to_csv(app_state.cleaned_data);download_file(A,'venues_all.csv',_P)
def export_1_visit(event):
	if not app_state.has_data():return
	B=app_state.parser.get_visit_distribution(app_state.cleaned_data);A=B[_I]
	if A:C=data_to_csv(A);download_file(C,'venues_1_visit.csv',_P);show_alert(f"Exported {len(A)} venues with 1 visit",_N)
	else:show_alert('No venues with 1 visit to export',_L)
def export_2_4_visits(event):
	if not app_state.has_data():return
	B=app_state.parser.get_visit_distribution(app_state.cleaned_data);A=B[_J]
	if A:C=data_to_csv(A);download_file(C,'venues_2-4_visits.csv',_P);show_alert(f"Exported {len(A)} venues with 2-4 visits",_N)
	else:show_alert('No venues with 2-4 visits to export',_L)
def export_5_plus_visits(event):
	if not app_state.has_data():return
	B=app_state.parser.get_visit_distribution(app_state.cleaned_data);A=B[_K]
	if A:C=data_to_csv(A);download_file(C,'venues_5+_visits.csv',_P);show_alert(f"Exported {len(A)} venues with 5+ visits",_N)
	else:show_alert('No venues with 5+ visits to export',_L)
def on_split_change(event):
	if app_state.has_data():update_results()
def reset_for_new_file():app_state.reset();document.getElementById(_B).style.display=_G;document.getElementById(_f).style.display=_G;document.getElementById(_Z).classList.remove(_D);document.getElementById(_b).value='';document.getElementById(_e).innerHTML=''
def init_app():E='hidden';D='change';A='click';C=document.getElementById(_b);C.addEventListener(D,create_proxy(handle_file));B=document.getElementById(_B);B.onclick=lambda e:C.click();B.addEventListener(_O,create_proxy(dragover));B.addEventListener('dragleave',create_proxy(dragleave));B.addEventListener('drop',create_proxy(drop));document.getElementById('exportAllBtn').addEventListener(A,create_proxy(export_all));document.getElementById('exportAllCSVBtn').addEventListener(A,create_proxy(export_all_csv));document.getElementById('export1Btn').addEventListener(A,create_proxy(export_1_visit));document.getElementById('export24Btn').addEventListener(A,create_proxy(export_2_4_visits));document.getElementById('export5Btn').addEventListener(A,create_proxy(export_5_plus_visits));window.resetForNewFile=create_proxy(reset_for_new_file);document.getElementById(_g).addEventListener(D,create_proxy(on_split_change));document.getElementById('pyscript-loading-message').classList.add(E);document.getElementById('main-content').classList.remove(E);console.log('PyScript initialized - using untappd_parser package!')