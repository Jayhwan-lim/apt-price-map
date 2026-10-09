// Kakao JavaScript key. It only works on domains registered in the Kakao app
// (Platform > Web), so it is safe to publish.
window.APP_CONFIG = {
  kakaoJsKey: "f3a267f3cd9a9612c8a98f814d668ec0",
  dataUrl: "data/complexes.json",
  regionUrl: (code) => `data/region/${code}.json`,
  yearUrl: (year) => `data/year/${year}.json`,
  tradesUrl: (code) => `data/trades/${code}.json`,
};
