import { defineConfig } from 'vitepress'
import { existsSync } from 'node:fs'

const site = 'https://cortex.getcortexlabs.com'
const repo = 'https://github.com/rafaelaugustos/cortex-claude'
const socialImage = `${site}/images/cortex-social.jpg`
const socialImageAlt = 'Cortex. Memory that remembers what matters. The Cortex icon, a puppy on a purple square.'
const cortex = '<a href="https://getcortexlabs.com/">Cortex Labs</a>'

const locales = {
  root: {
    dir: '',
    lang: 'en-US',
    hreflang: 'en',
    ogLocale: 'en_US',
    label: 'English',
    product: 'https://getcortexlabs.com/products/cortex/',
    description: 'Documentation for Cortex, a local memory server for Claude Code with progressive recall, a knowledge graph and a code graph, all on SQLite on your machine.',
    ui: {
      guide: 'Guide',
      github: 'GitHub',
      releases: 'Release notes',
      start: 'Getting started',
      intro: 'What is Cortex?',
      install: 'Install and update',
      how: 'How recall works',
      using: 'Using Cortex',
      tools: 'MCP tools',
      graph: 'The knowledge graph',
      code: 'The code graph',
      clusters: 'Clusters',
      capture: 'Hooks and auto-capture',
      scopes: 'Scopes',
      dashboard: 'The dashboard',
      reference: 'Reference',
      config: 'Configuration',
      privacy: 'Privacy',
      outline: 'On this page',
      edit: 'Edit this page on GitHub',
      message: 'Cortex is open source under the MIT license.',
      copyright: `Maintained by Rafael Augusto and ${cortex}`
    }
  },
  'pt-BR': {
    dir: 'pt-BR',
    lang: 'pt-BR',
    hreflang: 'pt-BR',
    ogLocale: 'pt_BR',
    label: 'Português',
    product: 'https://getcortexlabs.com/pt/products/cortex/',
    description: 'Documentação do Cortex, um servidor de memória local para o Claude Code com recall progressivo, grafo de conhecimento e grafo de código, tudo em SQLite na sua máquina.',
    ui: {
      guide: 'Guia',
      github: 'GitHub',
      releases: 'Novidades',
      start: 'Primeiros passos',
      intro: 'O que é o Cortex?',
      install: 'Instalar e atualizar',
      how: 'Como o recall funciona',
      using: 'Usando o Cortex',
      tools: 'Ferramentas MCP',
      graph: 'O grafo de conhecimento',
      code: 'O grafo de código',
      clusters: 'Clusters',
      capture: 'Hooks e captura automática',
      scopes: 'Escopos',
      dashboard: 'O dashboard',
      reference: 'Referência',
      config: 'Configuração',
      privacy: 'Privacidade',
      outline: 'Nesta página',
      edit: 'Editar esta página no GitHub',
      message: 'O Cortex é open source sob a licença MIT.',
      copyright: `Mantido por Rafael Augusto e ${cortex}`,
      docFooter: { prev: 'Anterior', next: 'Próxima' },
      darkModeSwitchLabel: 'Aparência',
      lightModeSwitchTitle: 'Mudar para o tema claro',
      darkModeSwitchTitle: 'Mudar para o tema escuro',
      sidebarMenuLabel: 'Menu',
      returnToTopLabel: 'Voltar ao topo',
      langMenuLabel: 'Mudar o idioma',
      notFound: { title: 'Página não encontrada', quote: 'Não lembro dessa página. Procurei em todas as camadas.', linkText: 'Voltar ao início' }
    },
    search: {
      button: { buttonText: 'Buscar', buttonAriaLabel: 'Buscar na documentação' },
      modal: {
        noResultsText: 'Nenhum resultado para',
        resetButtonTitle: 'Limpar busca',
        displayDetails: 'Exibir detalhes',
        footer: { selectText: 'selecionar', navigateText: 'navegar', closeText: 'fechar' }
      }
    }
  }
}

function themeFor(locale) {
  const prefix = locale.dir ? `/${locale.dir}` : ''
  const g = `${prefix}/guide`
  const { ui } = locale
  const { outline, edit, message, copyright, docFooter, darkModeSwitchLabel, lightModeSwitchTitle, darkModeSwitchTitle, sidebarMenuLabel, returnToTopLabel, langMenuLabel, notFound, ...t } = ui
  const labels = { docFooter, darkModeSwitchLabel, lightModeSwitchTitle, darkModeSwitchTitle, sidebarMenuLabel, returnToTopLabel, langMenuLabel, notFound }
  return {
    nav: [
      { text: t.guide, link: `${g}/`, activeMatch: `${g}/` },
      { text: t.releases, link: `${locale.product}releases/` }
    ],
    sidebar: {
      [`${g}/`]: [
        {
          text: t.start,
          items: [
            { text: t.intro, link: `${g}/` },
            { text: t.install, link: `${g}/install` },
            { text: t.how, link: `${g}/how-it-works` }
          ]
        },
        {
          text: t.using,
          items: [
            { text: t.tools, link: `${g}/tools` },
            { text: t.graph, link: `${g}/knowledge-graph` },
            { text: t.code, link: `${g}/code-graph` },
            { text: t.clusters, link: `${g}/clusters` },
            { text: t.capture, link: `${g}/capture` },
            { text: t.scopes, link: `${g}/scopes` },
            { text: t.dashboard, link: `${g}/dashboard` }
          ]
        },
        {
          text: t.reference,
          items: [
            { text: t.config, link: `${g}/configuration` },
            { text: t.privacy, link: `${g}/privacy` }
          ]
        }
      ]
    },
    outline: { level: [2, 3], label: outline },
    editLink: { pattern: `${repo}/edit/main/site/:path`, text: edit },
    footer: { message, copyright },
    ...Object.fromEntries(Object.entries(labels).filter(([, value]) => value))
  }
}

function localeOf(relativePath) {
  const dir = relativePath.split('/')[0]
  return Object.values(locales).find(locale => locale.dir && locale.dir === dir) || locales.root
}

function pageUrl(dir, sourcePath) {
  const path = sourcePath.replace(/index\.md$/, '').replace(/\.md$/, '')
  return dir ? `${site}/${dir}/${path}` : `${site}/${path}`
}

export default defineConfig({
  title: 'Cortex',
  description: locales.root.description,
  lang: locales.root.lang,
  cleanUrls: true,
  appearance: true,
  lastUpdated: false,
  sitemap: { hostname: site },
  head: [
    ['link', { rel: 'icon', type: 'image/png', href: '/favicon.png' }],
    ['link', { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' }],
    ['meta', { name: 'theme-color', content: '#9b30d9' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'Cortex' }],
    ['meta', { property: 'og:image', content: socialImage }],
    ['meta', { property: 'og:image:type', content: 'image/jpeg' }],
    ['meta', { property: 'og:image:width', content: '1200' }],
    ['meta', { property: 'og:image:height', content: '630' }],
    ['meta', { property: 'og:image:alt', content: socialImageAlt }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['meta', { name: 'twitter:image', content: socialImage }],
    ['meta', { name: 'twitter:image:alt', content: socialImageAlt }]
  ],
  transformHead({ pageData }) {
    if (pageData.isNotFound || pageData.relativePath === '404.md') {
      return [['meta', { name: 'robots', content: 'noindex, follow' }]]
    }
    const locale = localeOf(pageData.relativePath)
    const sourcePath = locale.dir ? pageData.relativePath.slice(locale.dir.length + 1) : pageData.relativePath
    const url = pageUrl(locale.dir, sourcePath)
    const title = pageData.title ? `${pageData.title} | Cortex` : 'Cortex'
    const description = pageData.description || locale.description
    const alternates = Object.values(locales)
      .filter(other => existsSync(new URL(`../${other.dir ? `${other.dir}/` : ''}${sourcePath}`, import.meta.url)))
    const structuredData = {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'WebSite',
          '@id': `${site}/#website`,
          name: 'Cortex',
          url: `${site}/`,
          inLanguage: Object.values(locales).map(other => other.hreflang)
        },
        {
          '@type': 'SoftwareApplication',
          '@id': `${site}/#app`,
          name: 'Cortex',
          applicationCategory: 'DeveloperApplication',
          operatingSystem: 'macOS, Linux, Windows',
          url: locales.root.product,
          offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
          license: 'https://spdx.org/licenses/MIT.html',
          codeRepository: repo,
          publisher: { '@type': 'Organization', name: 'Cortex Labs', url: 'https://getcortexlabs.com/' }
        },
        {
          '@type': 'WebPage',
          '@id': `${url}#webpage`,
          url,
          name: title,
          description,
          inLanguage: locale.hreflang,
          isPartOf: { '@id': `${site}/#website` },
          about: { '@id': `${site}/#app` },
          primaryImageOfPage: {
            '@type': 'ImageObject',
            contentUrl: socialImage,
            width: 1200,
            height: 630
          }
        }
      ]
    }
    return [
      ['link', { rel: 'canonical', href: url }],
      ...alternates.map(other => ['link', { rel: 'alternate', hreflang: other.hreflang, href: pageUrl(other.dir, sourcePath) }]),
      ['link', { rel: 'alternate', hreflang: 'x-default', href: pageUrl('', sourcePath) }],
      ['meta', { name: 'robots', content: 'index, follow, max-image-preview:large' }],
      ['meta', { property: 'og:url', content: url }],
      ['meta', { property: 'og:locale', content: locale.ogLocale }],
      ...alternates.filter(other => other !== locale).map(other => ['meta', { property: 'og:locale:alternate', content: other.ogLocale }]),
      ['meta', { property: 'og:title', content: title }],
      ['meta', { property: 'og:description', content: description }],
      ['meta', { name: 'twitter:title', content: title }],
      ['meta', { name: 'twitter:description', content: description }],
      ['script', { type: 'application/ld+json' }, JSON.stringify(structuredData).replace(/</g, '\\u003c')]
    ]
  },
  themeConfig: {
    logo: { src: '/logo.webp', alt: '' },
    socialLinks: [{ icon: 'github', link: repo }],
    search: {
      provider: 'local',
      options: {
        locales: Object.fromEntries(
          Object.entries(locales)
            .filter(([, locale]) => locale.search)
            .map(([key, locale]) => [key, { translations: locale.search }])
        )
      }
    }
  },
  locales: Object.fromEntries(
    Object.entries(locales).map(([key, locale]) => [
      key,
      {
        label: locale.label,
        lang: locale.lang,
        link: locale.dir ? `/${locale.dir}/` : '/',
        description: locale.description,
        themeConfig: themeFor(locale)
      }
    ])
  )
})
