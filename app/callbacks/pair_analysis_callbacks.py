from collections import defaultdict
from datetime import date as _date

import numpy as np
from dash import Input, Output, State, callback, clientside_callback, html, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

import app.services.pair_analysis_service as svc
import app.services.scatter_service as scatter_svc
from app.services.asset_service import get_assets


# ── Poblar dropdowns ──────────────────────────────────────────────────────────

@callback(
    Output("pair-asset1", "options"),
    Output("pair-asset2", "options"),
    Input("pair-asset1", "id"),
)
def load_options(_):
    opts = [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in get_assets()]
    return opts, opts


# ── Swap ──────────────────────────────────────────────────────────────────────

@callback(
    Output("pair-asset1", "value", allow_duplicate=True),
    Output("pair-asset2", "value", allow_duplicate=True),
    Input("pair-swap-btn", "n_clicks"),
    State("pair-asset1", "value"),
    State("pair-asset2", "value"),
    prevent_initial_call=True,
)
def swap_assets(_, a1, a2):
    if a1 is None and a2 is None:
        return no_update, no_update
    return a2, a1


# ── Mostrar/ocultar grado polinómico (clientside) ─────────────────────────────

clientside_callback(
    "function(t){ return t==='poly' ? {display:'block'} : {display:'none'}; }",
    Output("pair-poly-degree-col", "style"),
    Input("pair-trend-type", "value"),
)


# ── Scatter data store (se recalcula al cambiar activos o eventos) ────────────

@callback(
    Output("pair-scatter-data",  "data"),
    Output("pair-scatter-stats", "children"),
    Input("pair-asset1",       "value"),
    Input("pair-asset2",       "value"),
    Input("pair-show-events",  "value"),
)
def store_scatter_data(asset1_id, asset2_id, show_events_opt):
    if not asset1_id or not asset2_id:
        return None, ""

    if asset1_id == asset2_id:
        return None, dbc.Alert("Seleccioná dos activos diferentes.",
                               color="warning", className="mt-2 py-1",
                               style={"fontSize": "0.82rem"})

    pairs = scatter_svc.get_paired_prices(asset1_id, asset2_id)
    if not pairs:
        return None, dbc.Alert("Sin precios en común para ambos activos.",
                               color="warning", className="mt-2 py-1",
                               style={"fontSize": "0.82rem"})

    label1 = scatter_svc.get_asset_label(asset1_id)
    label2 = scatter_svc.get_asset_label(asset2_id)
    tick1  = label1.split(" — ")[0]
    tick2  = label2.split(" — ")[0]

    xs    = [p["p1"]   for p in pairs]
    ys    = [p["p2"]   for p in pairs]
    dates = [p["date"] for p in pairs]
    n     = len(pairs)

    hover = [
        f"<b>{dates[i]}</b><br>{tick1}: {xs[i]:.6g}<br>{tick2}: {ys[i]:.6g}"
        for i in range(n)
    ]

    show_events = "events" in (show_events_opt or [])
    events = scatter_svc.get_events_with_coords(asset1_id, asset2_id, pairs) if show_events else []

    event_color_for_date: dict[str, str] = {}
    for ev in events:
        sd = _date.fromisoformat(ev["start_date"])
        ed = _date.fromisoformat(ev["end_date"])
        for p in pairs:
            if sd <= _date.fromisoformat(p["date"]) <= ed:
                event_color_for_date[p["date"]] = ev["color"]

    normal_idx: list[int] = []
    event_by_color: dict[str, list[int]] = defaultdict(list)
    for i in range(n - 1):
        d = dates[i]
        if d in event_color_for_date:
            event_by_color[event_color_for_date[d]].append(i)
        else:
            normal_idx.append(i)

    corr = float(np.corrcoef(xs, ys)[0, 1]) if n > 2 else None
    stats = (
        f"N = {n} puntos  ·  {dates[0]} → {dates[-1]}"
        + (f"  ·  Correlación: {corr:.3f}" if corr is not None else "")
    )

    data = {
        "xs":           xs,
        "ys":           ys,
        "dates":        dates,
        "hover":        hover,
        "n":            n,
        "normal_idx":   normal_idx,
        "event_groups": [{"color": c, "indices": idx}
                         for c, idx in event_by_color.items()],
        "events":       events,
        "label1":       label1,
        "label2":       label2,
    }
    return data, stats


# ── Render clientside del gráfico de correlación ──────────────────────────────

clientside_callback(
    """
function(scatterData, trendType, polyDegree, logScale) {
  var EMPTY = {
    data: [],
    layout: {
      plot_bgcolor:'#111827', paper_bgcolor:'#111827',
      font:{color:'#dee2e6'},
      xaxis:{gridcolor:'#1f2937'}, yaxis:{gridcolor:'#1f2937'},
      margin:{l:60,r:20,t:20,b:50}
    }
  };
  if (!scatterData || !scatterData.xs) return EMPTY;

  var xs = scatterData.xs, ys = scatterData.ys;
  var n  = scatterData.n;

  function linReg(xx, yy) {
    var m=xx.length, sx=0,sy=0,sxy=0,sxx=0;
    for(var i=0;i<m;i++){sx+=xx[i];sy+=yy[i];sxy+=xx[i]*yy[i];sxx+=xx[i]*xx[i];}
    var d=m*sxx-sx*sx;
    if(Math.abs(d)<1e-12) return null;
    var a=(m*sxy-sx*sy)/d, b=(sy-a*sx)/m;
    return [a,b];
  }

  function gaussElim(A, b) {
    var m=b.length;
    var M=A.map(function(row,i){return row.concat([b[i]]);});
    for(var col=0;col<m;col++){
      var mx=col;
      for(var row=col+1;row<m;row++) if(Math.abs(M[row][col])>Math.abs(M[mx][col])) mx=row;
      var tmp=M[col]; M[col]=M[mx]; M[mx]=tmp;
      if(Math.abs(M[col][col])<1e-12) return null;
      for(var row=col+1;row<m;row++){
        var f=M[row][col]/M[col][col];
        for(var j=col;j<=m;j++) M[row][j]-=f*M[col][j];
      }
    }
    var x=new Array(m).fill(0);
    for(var i=m-1;i>=0;i--){
      x[i]=M[i][m];
      for(var j=i+1;j<m;j++) x[i]-=M[i][j]*x[j];
      x[i]/=M[i][i];
    }
    return x;
  }

  function polyReg(xx, yy, deg) {
    var d=deg+1, A=[], b=[];
    for(var i=0;i<d;i++){
      A.push(new Array(d).fill(0));
      var s=0; for(var k=0;k<xx.length;k++) s+=Math.pow(xx[k],i)*yy[k]; b.push(s);
    }
    for(var i=0;i<d;i++) for(var j=0;j<d;j++){
      var s=0; for(var k=0;k<xx.length;k++) s+=Math.pow(xx[k],i+j); A[i][j]=s;
    }
    return gaussElim(A,b);
  }

  function evalPoly(c, x) {
    var v=0; for(var i=0;i<c.length;i++) v+=c[i]*Math.pow(x,i); return v;
  }

  function computeR2(yy, yhat) {
    var mean=yy.reduce(function(a,b){return a+b;},0)/yy.length;
    var ssTot=yy.reduce(function(s,y){return s+(y-mean)*(y-mean);},0);
    var ssRes=yy.reduce(function(s,y,i){return s+(y-yhat[i])*(y-yhat[i]);},0);
    return ssTot>0 ? 1-ssRes/ssTot : 0;
  }

  function linspace(a,b,m) {
    var arr=[], step=(b-a)/(m-1);
    for(var i=0;i<m;i++) arr.push(a+i*step);
    return arr;
  }

  function computeTrend(xx, yy, type, deg) {
    var xMin=Math.min.apply(null,xx), xMax=Math.max.apply(null,xx);
    var xLine=linspace(xMin,xMax,300);
    var yLine,yhat,eq,r2Val;
    try {
      if(type==='linear') {
        var c=linReg(xx,yy); if(!c) return null;
        yhat=xx.map(function(x){return c[0]*x+c[1];});
        yLine=xLine.map(function(x){return c[0]*x+c[1];});
        eq='y = '+c[0].toPrecision(4)+'x + '+c[1].toPrecision(4);
      } else if(type==='log') {
        if(xx.some(function(v){return v<=0;})) return null;
        var lx=xx.map(Math.log), lxLine=xLine.map(Math.log);
        var c=linReg(lx,yy); if(!c) return null;
        yhat=lx.map(function(x){return c[0]*x+c[1];});
        yLine=lxLine.map(function(x){return c[0]*x+c[1];});
        eq='y = '+c[0].toPrecision(4)+'·ln(x) + '+c[1].toPrecision(4);
      } else if(type==='poly') {
        var d=Math.max(2,Math.min(10,parseInt(deg)||2));
        var c=polyReg(xx,yy,d); if(!c) return null;
        yhat=xx.map(function(x){return evalPoly(c,x);});
        yLine=xLine.map(function(x){return evalPoly(c,x);});
        eq='Polinómica grado '+d;
      } else if(type==='exp') {
        if(yy.some(function(v){return v<=0;})) return null;
        var ly=yy.map(Math.log);
        var c=linReg(xx,ly); if(!c) return null;
        yhat=xx.map(function(x){return Math.exp(c[0]*x+c[1]);});
        yLine=xLine.map(function(x){return Math.exp(c[0]*x+c[1]);});
        eq='y = '+Math.exp(c[1]).toPrecision(4)+'·e^('+c[0].toPrecision(4)+'x)';
      } else return null;
      r2Val=computeR2(yy,yhat);
      return {xLine:xLine, yLine:yLine, r2Val:r2Val, eq:eq};
    } catch(e){ return null; }
  }

  var traces = [];

  if(scatterData.normal_idx.length>0) {
    var ni=scatterData.normal_idx;
    traces.push({
      x:ni.map(function(i){return xs[i];}),
      y:ni.map(function(i){return ys[i];}),
      mode:'markers',
      marker:{
        size:5, color:ni, colorscale:'Plasma', opacity:0.7,
        showscale:true, cmin:0, cmax:n-1,
        colorbar:{
          title:{text:'Tiempo',side:'right',font:{size:10}},
          tickvals:[0,n-1],
          ticktext:[scatterData.dates[0],scatterData.dates[n-1]],
          tickfont:{size:9}, thickness:12, len:0.6
        }
      },
      hovertemplate:'%{customdata}<extra></extra>',
      customdata:ni.map(function(i){return scatterData.hover[i];}),
      showlegend:false
    });
  }

  scatterData.event_groups.forEach(function(g){
    traces.push({
      x:g.indices.map(function(i){return xs[i];}),
      y:g.indices.map(function(i){return ys[i];}),
      mode:'markers',
      marker:{size:7,color:g.color,opacity:0.9,line:{color:'#ffffff',width:0.8}},
      hovertemplate:'%{customdata}<extra></extra>',
      customdata:g.indices.map(function(i){return scatterData.hover[i];}),
      showlegend:false
    });
  });

  traces.push({
    x:[xs[n-1]], y:[ys[n-1]],
    mode:'markers+text',
    marker:{size:11,color:'#ef4444',symbol:'circle',line:{color:'#ffffff',width:1.5}},
    text:[scatterData.dates[n-1]],
    textposition:'top right',
    textfont:{color:'#ef4444',size:8},
    hovertemplate:scatterData.hover[n-1]+'<extra></extra>',
    showlegend:false
  });

  scatterData.events.forEach(function(ev){
    traces.push({
      x:[ev.p1], y:[ev.p2],
      mode:'markers+text',
      marker:{size:14,color:ev.color,symbol:'star',line:{color:'#1f2937',width:1}},
      text:[ev.name], textposition:'top center',
      textfont:{color:ev.color,size:8},
      hovertemplate:'<b>'+ev.name+'</b><br>'+ev.start_date+' → '+ev.end_date+'<extra></extra>',
      showlegend:false
    });
  });

  var annotations=[];
  if(trendType && trendType!=='none') {
    var tr=computeTrend(xs,ys,trendType,polyDegree);
    if(tr) {
      traces.push({
        x:tr.xLine, y:tr.yLine,
        mode:'lines',
        line:{color:'#facc15',width:1.5,dash:'dash'},
        name:tr.eq+'  (R² = '+tr.r2Val.toFixed(4)+')',
        hoverinfo:'skip'
      });
      annotations.push({
        xref:'paper',yref:'paper', x:0.01,y:0.99,
        text:'<b>R² = '+tr.r2Val.toFixed(4)+'</b>',
        showarrow:false,
        font:{size:11,color:'#facc15'},
        bgcolor:'rgba(0,0,0,0.5)', borderpad:4,
        xanchor:'left',yanchor:'top'
      });
    }
  }

  var at=logScale?'log':'linear';
  return {
    data:traces,
    layout:{
      plot_bgcolor:'#111827', paper_bgcolor:'#111827',
      font:{color:'#dee2e6',size:11},
      xaxis:{title:scatterData.label1,type:at,gridcolor:'#1f2937',
             zerolinecolor:'#4b5563',tickfont:{size:10}},
      yaxis:{title:scatterData.label2,type:at,gridcolor:'#1f2937',
             zerolinecolor:'#4b5563',tickfont:{size:10}},
      margin:{l:60,r:90,t:20,b:50},
      hovermode:'closest',
      annotations:annotations,
      legend:{x:0.01,y:0.01,font:{size:9,color:'#facc15'},
              bgcolor:'rgba(0,0,0,0)',xanchor:'left',yanchor:'bottom'}
    }
  };
}
""",
    Output("pair-graph-corr",   "figure"),
    Input("pair-scatter-data",  "data"),
    Input("pair-trend-type",    "value"),
    Input("pair-poly-degree",   "value"),
    Input("pair-log-axes",      "value"),
)


# ── Comparación y Ratio (requieren botón Analizar + rango de fechas) ──────────

@callback(
    Output("pair-graph-comp",  "figure"),
    Output("pair-graph-ratio", "figure"),
    Output("pair-alert",       "children"),
    Output("pair-alert",       "is_open"),
    Input("pair-btn-analizar", "n_clicks"),
    State("pair-asset1",       "value"),
    State("pair-asset2",       "value"),
    State("pair-date-from",    "date"),
    State("pair-date-to",      "date"),
    State("pair-log-scale",    "value"),
    prevent_initial_call=True,
)
def update_charts(n_clicks, asset1, asset2, date_from, date_to, log_scale):
    empty = go.Figure()

    if not asset1 or not asset2:
        return empty, empty, "Seleccioná ambos activos antes de analizar.", True

    if asset1 == asset2:
        return empty, empty, "Los dos activos deben ser distintos.", True

    from_date = _date.fromisoformat(date_from) if date_from else None
    to_date   = _date.fromisoformat(date_to)   if date_to   else None

    label1, label2, df1, df2, merged, error = svc.get_pair_data(
        asset1, asset2, from_date, to_date
    )

    if error and merged is None and df1 is None:
        return empty, empty, error, True

    fig_comp  = svc.build_comparison_fig(df1, df2, label1, label2, log_scale)
    fig_ratio = svc.build_ratio_fig(merged, label1, label2, log_scale) if merged is not None else empty

    if error:
        return fig_comp, fig_ratio, error, True

    return fig_comp, fig_ratio, no_update, False
