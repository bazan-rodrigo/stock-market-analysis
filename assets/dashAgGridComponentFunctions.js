/* Renderers de celda de las grillas ag-grid.
 *
 * REGLA DE ORO DE ESTE ARCHIVO: acá NO se decide nada. El servidor manda el
 * color, el umbral y el máximo contra el que se normaliza la barra; esto solo
 * los pinta. Así los criterios de negocio (verde desde +20, rojo desde −20, la
 * barra relativa a lo que estás viendo) siguen viviendo en Python, en un solo
 * lugar, y este archivo no puede derivar de la pantalla vieja.
 *
 * Los colores llegan por `cellRendererParams` desde app/components/ui_constants.py
 * — no hardcodear ninguno acá.
 */
var dagcomponentfuncs = (window.dashAgGridComponentFunctions =
    window.dashAgGridComponentFunctions || {});

/* Celda de score: número coloreado, con barra opcional.
 *
 * params esperados: barMax (0/ausente = sin barra), posTh, negTh, posColor,
 * negColor, neutralColor, emptyColor, barBg, plusSign.
 */
dagcomponentfuncs.ScoreCell = function (props) {
    var v = props.value;
    if (v === null || v === undefined || v === "") {
        return React.createElement(
            "span",
            { style: { color: props.emptyColor } },
            "—"
        );
    }

    var color =
        v >= props.posTh
            ? props.posColor
            : v <= props.negTh
            ? props.negColor
            : props.neutralColor;

    var texto = (props.plusSign && v > 0 ? "+" : "") + v.toFixed(1);
    var numero = React.createElement(
        "span",
        {
            style: {
                color: color,
                fontFamily: "monospace",
                fontSize: "0.74rem",
                verticalAlign: "middle",
            },
        },
        texto
    );

    if (!props.barMax) {
        return numero;
    }

    /* Misma fórmula que la pantalla anterior: 0 queda al 50%, así se ve de un
       vistazo de qué lado del cero está cada activo. */
    var pct = Math.round((v / props.barMax) * 50 + 50);
    pct = Math.max(0, Math.min(100, pct));

    var relleno = React.createElement("div", {
        style: {
            width: pct + "%",
            height: "100%",
            backgroundColor: color,
            borderRadius: "2px",
        },
    });
    var canal = React.createElement(
        "div",
        {
            style: {
                width: "40px",
                height: "8px",
                backgroundColor: props.barBg,
                borderRadius: "2px",
                overflow: "hidden",
                display: "inline-block",
                verticalAlign: "middle",
                marginRight: "4px",
            },
        },
        relleno
    );

    return React.createElement(
        "span",
        { style: { whiteSpace: "nowrap" } },
        canal,
        numero
    );
};

/* Celda de ticker: el símbolo enlaza al análisis del activo y "hist." al
 * historial de señales. Renderer propio y no markdown porque react-markdown 9
 * sacó linkTarget y los enlaces perderían el target=_blank que ya tenían.
 *
 * params: analysisHref, historyHref (con {id} a reemplazar), linkColor, dimColor.
 */
dagcomponentfuncs.TickerLinks = function (props) {
    var id = props.data ? props.data.asset_id : null;
    var enlace = function (href, texto, estilo) {
        return React.createElement(
            "a",
            {
                href: href.replace("{id}", id),
                target: "_blank",
                rel: "noopener",
                style: estilo,
            },
            texto
        );
    };

    if (id === null || id === undefined) {
        return React.createElement("span", null, props.value);
    }

    return React.createElement(
        "span",
        { style: { whiteSpace: "nowrap" } },
        enlace(
            props.analysisHref,
            React.createElement("strong", null, props.value),
            { color: props.linkColor, textDecoration: "none" }
        ),
        enlace(props.historyHref, " hist.", {
            color: props.dimColor,
            textDecoration: "none",
            fontSize: "0.68rem",
            marginLeft: "4px",
        })
    );
};
