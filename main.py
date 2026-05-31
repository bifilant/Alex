# -*- coding: utf-8 -*-
from __future__ import annotations
import json, math, time
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, Line, Ellipse
from kivy.metrics import dp
from kivy.properties import ListProperty, StringProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem

from calculations import PRESSURES, calculate_capillary, export_csv, rho_from_salinity, to_float, r4

Window.clearcolor = (0.055, 0.060, 0.070, 1)
Window.softinput_mode = "below_target"

BG=(0.055,0.060,0.070,1); PANEL=(0.105,0.115,0.135,1); PANEL2=(0.145,0.155,0.18,1)
TEXT=(0.94,0.95,0.97,1); MUTED=(0.68,0.71,0.76,1); GRID=(0.34,0.37,0.42,1)
ACC=(0.16,0.50,0.95,1); OK=(0.14,0.72,0.35,1); WARN=(0.98,0.57,0.12,1); MAN=(0.18,0.56,1.0,1); BAD=(0.90,0.22,0.22,1)


def sf(v, d=None):
    x=to_float(v,d)
    if x is None or (isinstance(x,float) and (math.isnan(x) or math.isinf(x))): return d
    return x

def fmt(v, n=3):
    x=sf(v)
    return "—" if x is None else f"{x:.{n}f}"

class Panel(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw); self.padding=dp(8); self.spacing=dp(6); self.bind(pos=self.bg,size=self.bg)
    def bg(self,*_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*PANEL); Rectangle(pos=self.pos,size=self.size)

class L(Label):
    def __init__(self, **kw):
        kw.setdefault('color', TEXT); kw.setdefault('font_size', dp(13)); kw.setdefault('halign','left'); kw.setdefault('valign','middle')
        super().__init__(**kw); self.bind(size=lambda i,*_: setattr(i,'text_size',i.size))

class Field(BoxLayout):
    def __init__(self, title, default="", **kw):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(42), spacing=dp(6), **kw)
        self.add_widget(L(text=title, size_hint_x=.45, halign='right', color=MUTED))
        self.input=TextInput(text=str(default), multiline=False, font_size=dp(16), foreground_color=TEXT, background_color=(.08,.09,.11,1), cursor_color=ACC, padding=[dp(8),dp(8)])
        self.add_widget(self.input)

class MiniButton(Button):
    def __init__(self, **kw):
        kw.setdefault('font_size', dp(13)); kw.setdefault('background_color', (.22,.24,.28,1)); kw.setdefault('color', TEXT)
        super().__init__(**kw)

class Curve(Widget):
    points=ListProperty([]); mode=StringProperty('ps'); app_ref=ObjectProperty(None)
    def __init__(self, **kw):
        super().__init__(**kw); self.drag_idx=None; self.bind(pos=lambda *_: self.draw(), size=lambda *_: self.draw(), points=lambda *_: self.draw())
    def area(self): return (self.x+dp(56), self.y+dp(36), max(dp(120), self.width-dp(86)), max(dp(110), self.height-dp(70)))
    def yrange(self):
        if self.mode=='ps': return 0,100,math.log10(.25),math.log10(10)
        vals=[sf(p[1]) for p in self.points if sf(p[1]) is not None]
        lo=min(vals) if vals else 0; hi=max(vals) if vals else 1
        if hi-lo<1e-9: hi=lo+1
        pad=(hi-lo)*.15
        return 0,10,max(0,lo-pad),hi+pad
    def ymap(self,y): return math.log10(max(.25,float(y))) if self.mode=='ps' else float(y)
    def d2s(self,x,y):
        ax,ay,w,h=self.area(); xmin,xmax,ymin,ymax=self.yrange(); yy=self.ymap(y)
        return ax+(float(x)-xmin)/(xmax-xmin)*w, ay+(yy-ymin)/(ymax-ymin)*h
    def s2d(self,sx,sy):
        ax,ay,w,h=self.area(); xmin,xmax,ymin,ymax=self.yrange()
        tx=max(0,min(1,(sx-ax)/w)); ty=max(0,min(1,(sy-ay)/h))
        x=xmin+tx*(xmax-xmin); y=ymin+ty*(ymax-ymin)
        if self.mode=='ps': y=10**y
        return x,y
    def txt(self,t,x,y,sz=10,c=MUTED,anchor='c'):
        lab=CoreLabel(text=str(t), font_size=dp(sz), color=c); lab.refresh(); tex=lab.texture; tw,th=tex.size
        px=x-tw/2 if anchor=='c' else (x-tw if anchor=='r' else x); py=y-th/2
        Color(1,1,1,1); Rectangle(texture=tex, pos=(px,py), size=tex.size)
    def draw(self):
        self.canvas.clear()
        with self.canvas:
            Color(.045,.050,.060,1); Rectangle(pos=self.pos,size=self.size)
            ax,ay,w,h=self.area(); Color(.10,.11,.13,1); Rectangle(pos=(ax,ay),size=(w,h))
            Color(*GRID)
            if self.mode=='ps':
                xt=[0,20,40,60,80,100]; yt=[.25,.5,1,3,5,7,10]
                for x in xt:
                    sx,_=self.d2s(x,.25); Line(points=[sx,ay,sx,ay+h],width=.7); self.txt(x,sx,ay-dp(15),9)
                for y in yt:
                    _,sy=self.d2s(0,y); Line(points=[ax,sy,ax+w,sy],width=.7); self.txt(y,ax-dp(8),sy,9,anchor='r')
                self.txt('S, %', ax+w/2, self.y+dp(13), 11, TEXT); self.txt('P, атм', self.x+dp(24), ay+h+dp(12), 11, TEXT)
            else:
                xt=[0,1,3,5,7,10]; xmin,xmax,ymin,ymax=self.yrange(); yt=[ymin+(ymax-ymin)*i/4 for i in range(5)]
                for x in xt:
                    sx,_=self.d2s(x,ymin); Line(points=[sx,ay,sx,ay+h],width=.7); self.txt(x,sx,ay-dp(15),9)
                for y in yt:
                    _,sy=self.d2s(0,y); Line(points=[ax,sy,ax+w,sy],width=.7); self.txt(fmt(y,1),ax-dp(8),sy,9,anchor='r')
                self.txt('P, атм', ax+w/2, self.y+dp(13), 11, TEXT); self.txt('R, Ом·м', self.x+dp(28), ay+h+dp(12), 11, TEXT)
            Color(.82,.86,.92,1); Line(rectangle=(ax,ay,w,h),width=1)
            valid=[]
            for x,y,col,idx,label,src in self.points:
                if sf(x) is None or sf(y) is None: continue
                sx,sy=self.d2s(x,y); valid.append((sx,sy,col,idx,label,src,x,y))
            valid.sort(key=lambda q:q[7] if self.mode=='ps' else q[6])
            if len(valid)>1:
                Color(.78,.82,.88,1); Line(points=[v for p in valid for v in p[:2]], width=1.4)
            for sx,sy,col,idx,label,src,x,y in valid:
                Color(*col); Ellipse(pos=(sx-dp(7),sy-dp(7)), size=(dp(14),dp(14)))
                self.txt(label, sx+dp(12), sy+dp(10), 9, TEXT, anchor='l')
    def nearest(self,touch):
        best=(None,999999)
        for x,y,col,idx,label,src in self.points:
            if sf(x) is None or sf(y) is None: continue
            sx,sy=self.d2s(x,y); d=(touch.x-sx)**2+(touch.y-sy)**2
            if d<best[1]: best=(idx,d)
        return best[0] if best[1] <= dp(38)**2 else None
    def on_touch_down(self,touch):
        if not self.collide_point(*touch.pos): return False
        self.drag_idx=self.nearest(touch)
        return self.drag_idx is not None
    def on_touch_move(self,touch):
        if self.drag_idx is None: return False
        x,y=self.s2d(touch.x,touch.y)
        if self.app_ref:
            if self.mode=='ps': self.app_ref.drag_s(self.drag_idx, max(0,min(100,x))/100)
            else: self.app_ref.drag_r(self.drag_idx, max(0,y))
        return True
    def on_touch_up(self,touch): self.drag_idx=None; return False

class FullApp(App):
    title='Капилляриметрия Full Android'
    def build(self):
        Window.orientation='landscape'
        self.fields={}; self.step_rows=[]; self.manual_s={}; self.manual_r={}; self.current=None
        root=BoxLayout(orientation='vertical', padding=dp(6), spacing=dp(5))
        header=BoxLayout(size_hint_y=None,height=dp(42)); header.add_widget(L(text='Капилляриметрия Android FULL', font_size=dp(22), bold=True, halign='center'))
        root.add_widget(header)
        self.tabs=TabbedPanel(do_default_tab=False, tab_width=dp(160), tab_height=dp(38), background_color=BG)
        root.add_widget(self.tabs)
        self.status=L(text='Готово', size_hint_y=None, height=dp(28), color=MUTED); root.add_widget(self.status)
        self.build_inputs(); self.build_steps(); self.build_graphs(); self.build_results(); self.build_files()
        Clock.schedule_once(lambda *_: self.update_rho(), .1)
        return root
    def tab(self,title):
        ti=TabbedPanelItem(text=title); self.tabs.add_widget(ti); return ti
    def build_inputs(self):
        t=self.tab('1. Исходные'); box=Panel(orientation='horizontal')
        left=Panel(orientation='vertical', size_hint_x=.55); right=Panel(orientation='vertical')
        box.add_widget(left); box.add_widget(right); t.add_widget(box)
        defs=[('D','D, мм',''),('L','L, мм',''),('salinity','Минерализация, г/л','0'),('rho','ρ, г/см³','0.9982'),('m_dry','m сух, г',''),('m_sat','m насыщ, г',''),('R0','R0, Ом·м',''),('R_water','Rw, Ом·м','1')]
        for k,title,default in defs:
            f=Field(title,default); self.fields[k]=f.input; left.add_widget(f); f.input.bind(text=lambda *_: self.live())
        ar=BoxLayout(size_hint_y=None,height=dp(42)); ar.add_widget(L(text='Авто ρ по минерализации', halign='right', color=MUTED)); self.auto_rho=CheckBox(active=True); ar.add_widget(self.auto_rho); left.add_widget(ar)
        self.auto_rho.bind(active=lambda *_: self.update_rho())
        btns=BoxLayout(size_hint_y=None,height=dp(48), spacing=dp(8));
        for txt,cb in [('Рассчитать',self.calculate),('Сброс drag',self.reset_drag),('Очистить ступени',self.clear_steps)]:
            b=MiniButton(text=txt); b.bind(on_press=lambda _,f=cb:f()); btns.add_widget(b)
        left.add_widget(btns)
        self.summary=L(text='Заполните данные и ступени.', font_size=dp(15)); right.add_widget(self.summary)
        self.archie=L(text='Archie: R0/Rt/Rw будут рассчитаны при наличии R0 и R.', font_size=dp(14), color=MUTED); right.add_widget(self.archie)
    def build_steps(self):
        t=self.tab('2. Ступени'); main=Panel(orientation='vertical'); t.add_widget(main)
        hdr=GridLayout(cols=4,size_hint_y=None,height=dp(34),spacing=dp(4))
        for h in ['P атм','Вкл','Масса, г','R, Ом·м']: hdr.add_widget(L(text=h,bold=True,halign='center'))
        main.add_widget(hdr); scroll=ScrollView(); grid=GridLayout(cols=4,size_hint_y=None,row_default_height=dp(48),spacing=dp(4)); grid.bind(minimum_height=grid.setter('height'))
        scroll.add_widget(grid); main.add_widget(scroll)
        for p in PRESSURES:
            grid.add_widget(L(text=str(p),halign='center'))
            cb=CheckBox(active=True); grid.add_widget(cb)
            m=TextInput(text='',multiline=False,font_size=dp(16),foreground_color=TEXT,background_color=(.08,.09,.11,1))
            r=TextInput(text='',multiline=False,font_size=dp(16),foreground_color=TEXT,background_color=(.08,.09,.11,1))
            grid.add_widget(m); grid.add_widget(r); self.step_rows.append({'P':p,'en':cb,'m':m,'R':r})
            cb.bind(active=lambda *_: self.live()); m.bind(text=lambda *_: self.live()); r.bind(text=lambda *_: self.live())
    def build_graphs(self):
        t=self.tab('3. Графики'); box=Panel(orientation='horizontal'); t.add_widget(box)
        p1=Panel(orientation='vertical'); p2=Panel(orientation='vertical'); box.add_widget(p1); box.add_widget(p2)
        p1.add_widget(L(text='P–S: drag по X меняет S%',bold=True,size_hint_y=None,height=dp(28)))
        self.gps=Curve(mode='ps', app_ref=self); p1.add_widget(self.gps)
        p2.add_widget(L(text='R–P: drag по Y меняет R',bold=True,size_hint_y=None,height=dp(28)))
        self.grp=Curve(mode='rp', app_ref=self); p2.add_widget(self.grp)
    def build_results(self):
        t=self.tab('4. Результаты'); box=Panel(orientation='vertical'); t.add_widget(box)
        self.res_scroll=ScrollView(); self.res_grid=GridLayout(cols=12,size_hint_y=None,row_default_height=dp(30),spacing=dp(2)); self.res_grid.bind(minimum_height=self.res_grid.setter('height'))
        self.res_scroll.add_widget(self.res_grid); box.add_widget(self.res_scroll)
    def build_files(self):
        t=self.tab('5. Файлы'); box=Panel(orientation='vertical'); t.add_widget(box)
        for txt,cb in [('Сохранить проект JSON',self.save_project),('Загрузить проект JSON',self.load_project),('Экспорт CSV',self.export_csv)]:
            b=MiniButton(text=txt,size_hint_y=None,height=dp(48)); b.bind(on_press=lambda _,f=cb:f()); box.add_widget(b)
        self.file_info=L(text='Файлы сохраняются в папку приложения Android. CSV можно забрать через файловый менеджер/экспорт.',color=MUTED); box.add_widget(self.file_info)
    def update_rho(self):
        if self.auto_rho.active:
            self.fields['rho'].text=f"{rho_from_salinity(self.fields['salinity'].text):.4f}"
    def live(self):
        if getattr(self,'auto_rho',None) and self.auto_rho.active: self.update_rho()
    def data(self): return {k:v.text for k,v in self.fields.items()}
    def steps(self): return [{'P':r['P'],'en':r['en'].active,'m':r['m'].text,'R':r['R'].text} for r in self.step_rows]
    def calculate(self):
        try:
            self.current=calculate_capillary(self.data(), self.steps()); self.apply_manual(); self.render(); self.status.text='Расчёт выполнен'
        except Exception as e: self.status.text='Ошибка: '+str(e)
    def apply_manual(self):
        if not self.current: return
        for i,v in self.manual_s.items():
            if 0<=i<len(self.current['rows']): self.current['rows'][i]['S']=v; self.current['rows'][i]['S_pct']=v*100; self.current['rows'][i]['mSrc']='drag'
        for i,v in self.manual_r.items():
            if 0<=i<len(self.current['rows']): self.current['rows'][i]['R']=v; self.current['rows'][i]['rSrc']='drag'
    def render(self):
        rows=self.current['rows']; s=self.current['summary']
        self.summary.text=(f"Vобр={r4(s.get('Vobr'))} см³ | Vp={r4(s.get('Vp'))} см³\n"
            f"Kво={r4(s.get('Kvo'))} | Sov={r4(s.get('Sov'))}\nKпор={r4(s.get('Kpor'))} | Kпор эфф={r4(s.get('Kpor_eff'))}\nn Archie={r4(s.get('n'))}")
        self.archie.text='R0=%s | Rw=%s | m_water=%s' % (r4(s.get('R0')), self.fields['R_water'].text, r4(s.get('m_water_total')))
        self.res_grid.clear_widgets(); headers=['P','m','m src','S%','R','R src','Vv','λ','I','logSw','logI','H м']
        for h in headers: self.res_grid.add_widget(L(text=h,bold=True,halign='center',font_size=dp(10)))
        for r in rows:
            vals=[r.get('P'),fmt(r.get('m'),4),r.get('mSrc'),fmt(r.get('S_pct'),2),fmt(r.get('R'),4),r.get('rSrc'),fmt(r.get('Vv'),4),fmt(r.get('lam'),4),fmt(r.get('I'),4),fmt(r.get('log_Sw'),4),fmt(r.get('log_I'),4),fmt(r.get('H_m'),3)]
            for v in vals: self.res_grid.add_widget(L(text=str(v),font_size=dp(10),halign='center'))
        ps=[]; rp=[]
        for i,r in enumerate(rows):
            cm=MAN if i in self.manual_s else (OK if r.get('mSrc')=='измерено' else WARN)
            cr=MAN if i in self.manual_r else (OK if r.get('rSrc')=='измерено' else WARN)
            ps.append((r.get('S_pct'),r.get('P'),cm,i,str(r.get('P')),r.get('mSrc')))
            rp.append((r.get('P'),r.get('R'),cr,i,str(r.get('P')),r.get('rSrc')))
        self.gps.points=ps; self.grp.points=rp
    def drag_s(self,i,s): self.manual_s[i]=s; self.apply_manual(); self.render(); self.status.text='S изменено drag'
    def drag_r(self,i,r): self.manual_r[i]=r; self.apply_manual(); self.render(); self.status.text='R изменено drag'
    def reset_drag(self): self.manual_s.clear(); self.manual_r.clear(); self.calculate()
    def clear_steps(self):
        for r in self.step_rows: r['m'].text=''; r['R'].text=''; r['en'].active=True
        self.manual_s.clear(); self.manual_r.clear(); self.current=None; self.gps.points=[]; self.grp.points=[]; self.res_grid.clear_widgets(); self.status.text='Ступени очищены'
    def project_path(self): return Path(self.user_data_dir)/'capill_project.json'
    def save_project(self):
        obj={'data':self.data(),'steps':self.steps(),'manual_s':self.manual_s,'manual_r':self.manual_r,'time':time.time()}
        p=self.project_path(); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8'); self.file_info.text='Сохранено: '+str(p)
    def load_project(self):
        p=self.project_path()
        try:
            obj=json.loads(p.read_text(encoding='utf-8'))
            for k,v in obj.get('data',{}).items():
                if k in self.fields: self.fields[k].text=str(v)
            for src,dst in zip(obj.get('steps',[]), self.step_rows):
                dst['en'].active=bool(src.get('en',True)); dst['m'].text=str(src.get('m') or ''); dst['R'].text=str(src.get('R') or '')
            self.manual_s={int(k):float(v) for k,v in obj.get('manual_s',{}).items()}; self.manual_r={int(k):float(v) for k,v in obj.get('manual_r',{}).items()}
            self.calculate(); self.file_info.text='Загружено: '+str(p)
        except Exception as e: self.file_info.text='Ошибка загрузки: '+str(e)
    def export_csv(self):
        if not self.current: self.calculate()
        if not self.current: return
        p=Path(self.user_data_dir)/('capill_results_%d.csv'%int(time.time()))
        export_csv(p,self.current); self.file_info.text='CSV: '+str(p)

if __name__=='__main__':
    FullApp().run()
