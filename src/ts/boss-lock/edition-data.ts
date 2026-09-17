/**
 * boss-lock / edition-data — Locale-specific data pools for boss-mode
 * financial newspaper editions.
 *
 * Extracted from edition.ts to keep file sizes manageable.
 */

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

/** Base index-quote deltas keyed by ticker symbol. */
export interface ThemeBase {
  DOW: number;
  NAS: number;
  SPX: number;
  FTSE: number;
  USDX: number;
}

/** A content theme that drives headline, sidebar stories, and quote drift. */
export interface Theme {
  headline: string;
  subhead: string;
  stories: string[];
  base: ThemeBase;
}

/** The fully-assembled edition object consumed by the template renderer. */
export interface BossModeEdition {
  brand: string;
  sectionLine: string[];
  deskLabel: string;
  byline: string;
  showBreaking: boolean;
  breakingText: string;
  headline: string;
  subhead: string;
  stories: string[];
  quotes: string[];
}

/* ------------------------------------------------------------------ */
/*  Brands                                                             */
/* ------------------------------------------------------------------ */

export const BRANDS_JA: string[] = [
  'Nikkei-ish Times', 'Keizai Observer', 'Shachiku Standard',
  'Kabushiki Chronicle', 'Ledger Shinpo', 'Toushi Weekly',
  'The Wall Treat Journal', 'Bloomsburg Review', 'Fishing Tyres',
  'The Econonomist', 'Barrons Weekday', 'Dow Janes Newswire',
  'Nihon Zaikai Shimbun', 'Toyo Keizai Onrain', 'Markit Watch',
  'Investors Dairy', 'The Motley Fuel', 'Zaim Asia Review',
  'FAX NEWS', 'BVC WORLD NEWS', 'MPR Breakable NEWS',
  'CBG NEWS', 'Ski News', 'ABG NEWS and Headlines',
  'PB$ Public Broadband for $',
];
export const BRANDS_EN: string[] = [
  'Nikkei-ish Times', 'Quarterly Panic', 'Alpha Desk Review',
  'The Beige Ledger', 'Market Sentinel', 'Capital Chronicle',
  'The Wall Treat Journal', 'Bloomsburg Review', 'Reutors Wire', 'Fishing Tyres',
  'The Econonomist', 'Barrons Weekday', 'Dow Janes Newswire',
  'Markit Watch', 'Investors Dairy', 'The Motley Fuel',
  'CNBN World', 'Forex Factory Outlet', 'The Guardiun Business',
  'FAX NEWS', 'BVC WORLD NEWS', 'MPR Breakable NEWS',
  'CBG NEWS', 'Ski News', 'ABG NEWS and Headlines',
  'PB$ Public Broadband for $',
];
export const BRANDS_ZH: string[] = [
  'Nikkei-ish Times', '\u8CA1\u7D93\u89C0\u5BDF\u5831', '\u4E9E\u592A\u7D93\u6FDF\u9031\u520A',
  'The Wall Treat Journal', 'Bloomsburg Review', '\u74B0\u7403\u8CA1\u8A0A',
  '\u80A1\u5E02\u6674\u96E8\u8868', 'Markit Watch', 'Investors Dairy',
  'FAX NEWS', 'BVC WORLD NEWS', 'MPR Breakable NEWS',
  'CBG NEWS', 'Ski News', 'ABG NEWS and Headlines',
  'PB$ Public Broadband for $', '\u6771\u65B9\u8CA1\u5BCC\u65E5\u5831',
  '\u65B0\u83EF\u8CA1\u7D93\u5FEB\u8A0A', '\u9CF3\u51F0\u8CA1\u7D93\u901F\u5831', '\u7D93\u6FDF\u53C3\u8003\u5831',
];
export const BRANDS_KO: string[] = [
  'Nikkei-ish Times', '\uB9E4\uC77C\uACBD\uC81C \uD0C0\uC784\uC988', '\uD55C\uAD6D\uACBD\uC81C \uC635\uC800\uBC84',
  'The Wall Treat Journal', 'Bloomsburg Review', '\uC544\uC2DC\uC544\uACBD\uC81C \uB9AC\uBDF0',
  '\uC8FC\uC2DD\uC2DC\uC7A5 \uD06C\uB85C\uB2C8\uD074', 'Markit Watch', 'Investors Dairy',
  'FAX NEWS', 'BVC WORLD NEWS', 'MPR Breakable NEWS',
  'CBG NEWS', 'Ski News', 'ABG NEWS and Headlines',
  'PB$ Public Broadband for $', '\uC11C\uC6B8\uD30C\uC774\uB09C\uC2A4 \uB370\uC77C\uB9AC',
  '\uCF54\uC2A4\uD53C \uC13C\uD2F0\uB12C', '\uC99D\uAD8C\uAC00 \uC704\uD074\uB9AC', '\uB514\uC9C0\uD138 \uBA38\uB2C8\uD22C\uB370\uC774',
];

/* ------------------------------------------------------------------ */
/*  Sections & Labels                                                  */
/* ------------------------------------------------------------------ */

export const SECTIONS: string[] = [
  'World', 'Markets', 'Economy', 'Companies', 'Tech', 'Policy', 'Opinion',
  'Commodities', 'Currencies', 'Fixed Income', 'Regulation', 'IPO Watch',
  'Personal Finance', 'Real Estate', 'Climate & Energy',
];

export const LABELS: string[] = [
  'Analysis', 'Briefing', 'Markets Live', 'Morning Note', 'Desk View',
  'Deep Dive', 'Weekly Wrap', 'Data Room', 'The Big Read', 'Special Report',
  'Macro Pulse', 'Opening Bell', 'Closing Summary',
];

/* ------------------------------------------------------------------ */
/*  Bylines                                                            */
/* ------------------------------------------------------------------ */

export const BYLINES_JA: string[] = [
  'By M. Tanaka', 'By Desk Tokyo', 'By K. Sato', 'By A. Mori',
  'By Y. Suzuki, Kabutocho Bureau', 'By N. Watanabe, Asia Markets',
  'By T. Yamamoto', 'By R. Takahashi, Policy Desk',
  'By S. Nakamura & H. Ito', 'By Special Correspondent, Osaka',
];
export const BYLINES_EN: string[] = [
  'By Lionel Beige', 'By Markets Desk', 'By A. Ledger', 'By J. Parity',
  'By C. Margin, London Bureau', 'By R. Dividend & S. Yield',
  'By P. Spreadworth, Frankfurt', 'By Capital Markets Team',
  'By D. Leverage, New York', 'By M. Coupon, Fixed Income Desk',
];
export const BYLINES_ZH: string[] = [
  'By W. Chen', 'By Markets Desk Shanghai', 'By L. Wang', 'By H. Zhang',
  'By T. Liu, Hong Kong Bureau', 'By Y. Huang & J. Lin',
  'By S. Wu, Taipei', 'By Capital Markets Team Asia',
  'By M. Zhao, Beijing', 'By R. Li, Fixed Income Desk',
];
export const BYLINES_KO: string[] = [
  'By J. Kim', 'By Markets Desk Seoul', 'By S. Park', 'By H. Lee',
  'By M. Choi, Seoul Bureau', 'By Y. Jung & D. Kang',
  'By W. Han, Yeouido', 'By Capital Markets Team Korea',
  'By J. Yoon, Busan', 'By S. Lim, Fixed Income Desk',
];

/* ------------------------------------------------------------------ */
/*  Breaking news                                                      */
/* ------------------------------------------------------------------ */

export const BREAKING_JA: string[] = [
  '\u901F\u5831: \u6307\u6570\u5148\u7269\u304C\u6025\u53CD\u767A',
  '\u901F\u5831: \u4E3B\u8981\u4E2D\u9280\u304C\u5171\u540C\u58F0\u660E\u3092\u793A\u5506',
  '\u901F\u5831: \u91CD\u8981\u7D71\u8A08\u3092\u524D\u306B\u70BA\u66FF\u304C\u5909\u52D5',
  '\u901F\u5831: \u5927\u624B\u30C6\u30C3\u30AF\u4F01\u696D\u304C\u8CB7\u53CE\u3092\u767A\u8868',
  '\u901F\u5831: \u539F\u6CB9\u4FA1\u683C\u304C5%\u8D85\u306E\u6025\u843D\u3001\u4E2D\u6771\u60C5\u52E2\u3092\u53D7\u3051',
  '\u901F\u5831: \u7C73\u96C7\u7528\u7D71\u8A08\u304C\u4E88\u60F3\u3092\u5927\u5E45\u306B\u4E0A\u56DE\u308B',
  '\u901F\u5831: \u6B27\u5DDE\u4E2D\u9280\u304C\u4E88\u60F3\u5916\u306E\u5229\u4E0B\u3052\u3092\u6C7A\u5B9A',
  '\u901F\u5831: \u534A\u5C0E\u4F53\u5927\u624B\u304C\u696D\u7E3E\u4E88\u60F3\u3092\u4E0A\u65B9\u4FEE\u6B63',
  '\u901F\u5831: \u91D1\u4FA1\u683C\u304C\u53F2\u4E0A\u6700\u9AD8\u5024\u3092\u66F4\u65B0',
  '\u901F\u5831: \u65E5\u7D4C\u5E73\u5747\u304C\u4E00\u66421000\u5186\u8D85\u306E\u4E0B\u843D',
];
export const BREAKING_EN: string[] = [
  'Breaking: Equity futures swing sharply higher',
  'Breaking: Major central banks signal joint statement',
  'Breaking: FX moves ahead of key macro release',
  'Breaking: Major tech firm announces surprise acquisition',
  'Breaking: Crude oil drops 5% on supply concerns',
  'Breaking: US payrolls smash expectations, yields spike',
  'Breaking: ECB delivers surprise rate cut',
  'Breaking: Chipmaker raises full-year guidance sharply',
  'Breaking: Gold hits record high amid safe-haven demand',
  'Breaking: Treasury 10Y yield breaches 5% for first time since 2007',
];
export const BREAKING_ZH: string[] = [
  '\u5FEB\u8BAF: \u80A1\u6307\u671F\u8D27\u5927\u5E45\u53CD\u5F39',
  '\u5FEB\u8BAF: \u4E3B\u8981\u592E\u884C\u6697\u793A\u5C06\u53D1\u8868\u8054\u5408\u58F0\u660E',
  '\u5FEB\u8BAF: \u91CD\u8981\u6570\u636E\u516C\u5E03\u524D\u6C47\u7387\u6CE2\u52A8\u52A0\u5267',
  '\u5FEB\u8BAF: \u5927\u578B\u79D1\u6280\u516C\u53F8\u5BA3\u5E03\u6536\u8D2D\u8BA1\u5212',
  '\u5FEB\u8BAF: \u539F\u6CB9\u4EF7\u683C\u66B4\u8DCC\u90095%\uFF0C\u53D7\u4E2D\u4E1C\u5C40\u52BF\u5F71\u54CD',
  '\u5FEB\u8BAF: \u7F8E\u56FD\u5C31\u4E1A\u6570\u636E\u5927\u5E45\u8D85\u51FA\u9884\u671F',
  '\u5FEB\u8BAF: \u6B27\u6D32\u592E\u884C\u610F\u5916\u5BA3\u5E03\u964D\u606F',
  '\u5FEB\u8BAF: \u534A\u5BFC\u4F53\u5DE8\u5934\u4E0A\u8C03\u5168\u5E74\u4E1A\u7EE9\u9884\u671F',
  '\u5FEB\u8BAF: \u907F\u9669\u9700\u6C42\u63A8\u52A8\u91D1\u4EF7\u521B\u5386\u53F2\u65B0\u9AD8',
  '\u5FEB\u8BAF: \u4E9A\u592A\u80A1\u5E02\u5168\u7EBF\u8D70\u4F4E\uFF0C\u8D38\u6613\u6469\u64E6\u5FE7\u8651\u5347\u6E29',
];
export const BREAKING_KO: string[] = [
  '\uC18D\uBCF4: \uC8FC\uAC00\uC9C0\uC218 \uC120\uBB3C \uAE09\uBC18\uB4F1',
  '\uC18D\uBCF4: \uC8FC\uC694 \uC911\uC559\uC740\uD589 \uACF5\uB3D9\uC131\uBA85 \uC2DC\uC0AC',
  '\uC18D\uBCF4: \uC8FC\uC694 \uACBD\uC81C\uC9C0\uD45C \uBC1C\uD45C \uC55E\uB450\uACE0 \uD658\uC728 \uBCC0\uB3D9',
  '\uC18D\uBCF4: \uB300\uD615 \uD14C\uD06C\uAE30\uC5C5 \uC778\uC218 \uBC1C\uD45C',
  '\uC18D\uBCF4: \uC6D0\uC720 \uAC00\uACA9 5% \uC774\uC0C1 \uAE09\uB77D, \uC911\uB3D9 \uC815\uC138 \uC601\uD5A5',
  '\uC18D\uBCF4: \uBBF8\uAD6D \uACE0\uC6A9\uC9C0\uD45C \uC608\uC0C1 \uD06C\uAC8C \uC0C1\uD68C',
  '\uC18D\uBCF4: \uC720\uB7FD\uC911\uC559\uC740\uD589 \uC608\uC0C1 \uBC16 \uAE08\uB9AC \uC778\uD558 \uACB0\uC815',
  '\uC18D\uBCF4: \uBC18\uB3C4\uCCB4 \uB300\uAE30\uC5C5 \uC5F0\uAC04 \uC2E4\uC801 \uC804\uB9DD \uC0C1\uD5A5',
  '\uC18D\uBCF4: \uAE08 \uAC00\uACA9 \uC0AC\uC0C1 \uCD5C\uACE0\uAC00 \uACBD\uC2E0',
  '\uC18D\uBCF4: \uCF54\uC2A4\uD53C \uC7A5\uC911 100\uD3EC\uC778\uD2B8 \uC774\uC0C1 \uD558\uB77D',
];

/* ------------------------------------------------------------------ */
/*  Ticker symbols                                                     */
/* ------------------------------------------------------------------ */

export const TICKERS: (keyof ThemeBase)[] = ['DOW', 'NAS', 'SPX', 'FTSE', 'USDX'];
