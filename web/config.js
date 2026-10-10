// Kakao JavaScript key. It only works on domains registered in the Kakao app
// (Platform > Web), so it is safe to publish.
window.APP_CONFIG = {
  kakaoJsKey: "f3a267f3cd9a9612c8a98f814d668ec0",
  dataUrl: "data/complexes.json",
  mapIndexUrl: "data/mapindex/all.json",
  mapParts: (i) => `data/mapindex/part-${String(i).padStart(2, "0")}.json`,
  mapPartCount: 12,
  regionUrl: (code) => `data/region/${code}.json`,
  yearUrl: (year) => `data/year/${year}.json`,
  tradesUrl: (code) => `data/trades/${code}.json`,
};
