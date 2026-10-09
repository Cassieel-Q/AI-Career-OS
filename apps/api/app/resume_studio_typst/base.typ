#let data = json("resume.json")
#let tpl = json("template.json")
#let accent = rgb(tpl.accent)
#let compact = tpl.density == "compact"
#let open = tpl.density == "open"
#let gap = if compact { 3pt } else if open { 9pt } else { 6pt }
#let fonts = if tpl.language == "zh" {
  ("Microsoft YaHei", "Noto Sans CJK SC", "Libertinus Sans")
} else {
  ("Libertinus Sans", "Arial")
}

#set page(paper: "a4", margin: (x: if compact { 34pt } else { 43pt }, y: if compact { 31pt } else { 39pt }))
#set text(font: fonts, size: if compact { 8.5pt } else if open { 9.5pt } else { 9pt }, lang: tpl.language)
#set par(leading: 0.7em)

#let visible(n) = n != none and n.claim_status != "OMITTED" and n.text != ""
#let field(n) = if visible(n) { [#metadata(n.id) #n.text] } else { [] }
#let contact = [#field(data.basics.phone) #h(9pt) #field(data.basics.email) #h(9pt) #field(data.basics.location)]

#let entry-body(e) = [
  #if visible(e.subtitle) { [#text(fill: rgb("#5c6475"))[#field(e.subtitle)] #linebreak()] }
  #for bullet in e.bullets {
    if visible(bullet) { [#text(fill: accent)[•] #field(bullet) #linebreak()] }
  }
]

#let entry(e) = {
  if e.status == "OMITTED" { [] } else if tpl.style == "timeline" {
    block(above: gap, below: gap)[
      #grid(columns: (85pt, 1fr), gutter: 8pt,
        [#text(fill: accent, size: 8pt)[#field(e.date)]],
        [#text(weight: "bold")[#field(e.title)] #linebreak() #entry-body(e)])
    ]
  } else {
    block(above: gap, below: gap)[
      #grid(columns: (1fr, auto), gutter: 6pt,
        [#text(weight: "bold")[#field(e.title)]],
        [#text(fill: rgb("#5c6475"), size: 8pt)[#field(e.date)]])
      #entry-body(e)
    ]
  }
}

#let section-heading(sec) = {
  if tpl.style == "minimal" {
    block(above: 16pt, below: 5pt)[#text(size: 10pt, weight: "bold")[#field(sec.title)]]
  } else if tpl.style == "editorial" {
    block(above: 14pt, below: 4pt)[
      #text(size: 13pt, weight: "bold", fill: accent)[#field(sec.title)]
      #line(length: 100%, stroke: (paint: accent, thickness: 0.5pt))
    ]
  } else if tpl.style == "banner" {
    block(above: 8pt, below: 4pt, fill: accent, inset: (x: 6pt, y: 3pt))[
      #text(fill: white, weight: "bold")[#field(sec.title)]
    ]
  } else if tpl.style == "compact" {
    block(above: 5pt, below: 3pt)[
      #text(weight: "bold", fill: accent)[#field(sec.title)]
      #line(length: 100%, stroke: (paint: accent, thickness: 0.7pt))
    ]
  } else {
    block(above: 10pt, below: 4pt)[
      #text(size: 10pt, weight: "bold", fill: accent)[#field(sec.title)]
      #line(length: 100%, stroke: (paint: accent, thickness: if tpl.style == "modern" { 1.4pt } else { 0.7pt }))
    ]
  }
}

#let section(sec) = {
  let entries = sec.entries.filter(e => e.status != "OMITTED")
  if entries.len() == 0 { [] } else {
    if sec.kind == "skills" {
      let groups = (
        (key: "product", label: "产品能力"),
        (key: "ai", label: "AI 产品能力"),
        (key: "tools", label: "技术与工具"),
        (key: "language", label: "语言能力"),
        (key: "other", label: "其他技能"),
      )
      [#section-heading(sec)
        #block(above: 2pt, below: gap)[
          #for group in groups {
            let members = entries.filter(e => e.skill_category == group.key)
            if members.len() > 0 {
              [#text(weight: "bold")[#group.label：]
                #for (i, member) in members.enumerate() {
                  field(member.title)
                  if visible(member.subtitle) { [（#field(member.subtitle)）] }
                  for bullet in member.bullets {
                    if visible(bullet) { [（#field(bullet)）] }
                  }
                  if i < members.len() - 1 { [、] }
                }
                #if group.key != "other" { [；] }
              ]
            }
          }
        ]
      ]
    } else {
      [#section-heading(sec) #for e in entries { entry(e) }]
    }
  }
}

#if tpl.header == "center" {
  align(center)[
    #text(size: if tpl.style == "grid" { 21pt } else { 19pt }, weight: "bold", fill: accent)[#field(data.basics.name)]
    #linebreak()
    #contact
  ]
} else if tpl.header == "banner" {
  block(fill: accent, inset: 11pt, width: 100%)[
    #text(size: 19pt, weight: "bold", fill: white)[#field(data.basics.name)]
    #linebreak()
    #text(fill: white)[#contact]
  ]
} else if tpl.header == "large" {
  block(below: 10pt)[
    #text(size: 27pt, weight: "bold", fill: accent)[#field(data.basics.name)]
    #linebreak()
    #contact
  ]
} else {
  block(below: 7pt)[
    #text(size: if compact { 17pt } else { 20pt }, weight: "bold", fill: accent)[#field(data.basics.name)]
    #linebreak()
    #contact
  ]
}

#if tpl.style == "sidebar" {
  grid(columns: (0.36fr, 0.64fr), gutter: 17pt,
    [#for sec in data.sections.filter(s => s.kind != "experience") { section(sec) }],
    [#for sec in data.sections.filter(s => s.kind == "experience") { section(sec) }])
} else if tpl.style == "grid" {
  grid(columns: (0.5fr, 0.5fr), gutter: 16pt,
    [#for sec in data.sections.filter(s => s.kind == "education" or s.kind == "skills") { section(sec) }],
    [#for sec in data.sections.filter(s => s.kind != "education" and s.kind != "skills") { section(sec) }])
} else {
  for sec in data.sections { section(sec) }
}
