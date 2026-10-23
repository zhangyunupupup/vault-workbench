# 官网型号图片接入

核对日期：2026-10-24。来源：[USSA VAULT 官网](https://www.ussadesign.com/pages/vault)及其[型号选型页](https://www.ussadesign.com/pages/vault?view=vault-model)。

官网页面的 `window.VaultShopifyConfig.assets` 提供原始素材路径与 Shopify CDN 地址的明确对应关系。采用 `vault-family-chooser/images/drawers/{型号}.jpg` 与 `vault-family-chooser/images/sustainers/{型号}.jpg` 对应的原始型号图，未采用 `images/studio/` 中的 AI 辅助展示图。

接入范围为 S/M/L/XL × 深度3–7 × 抽屉/翻盖箱，共40张，约1.92 MiB。CDN URL 虽以 `.webp` 结尾，本次响应实际为 JPEG；本地文件按实际编码保存为 `.jpg`，未进行裁切、重绘或重新编码。素材存于 `web/assets/models/`，逐图的官网地址、原始逻辑路径、字节数、SHA-256 与匹配范围保存在 `web/assets/official-images.json`。

官网原图通常是一组同型号不同高度的箱体，XL 原图通常为浅款，因此匹配范围限定为「型号系列图」。高度、内抽组合、顶盖、分隔与移动配件仍以用户所选配置及零件清单为准。网页使用1U/2U/4U的显示，不据此改变本地资料库的1F/2F/4F配方规则。

官网还列出 L23 等双列相关素材，但本轮未确认其与本地 L²/XL² 文件版本的完整对应关系，因此双列型号继续使用注明范围的装配示意，避免借用普通L/XL图片。图片读取失败时也会回退，不影响打印配置和打包。

界面提供大图和官网原图来源入口；所有日常显示使用本地资源，页面不会因切换型号而连接第三方图片服务。

验证：21项单元测试通过；40张图片均可解码，来源、路径、数量及校验值检查通过。浏览器逐一切换40个型号，并检查6个常用预选、大图、双列回退及未缓存的缺图回退。详细记录见 `output/review/official-image-verification.json`。官网素材属于USSA，保留其来源与权属说明。
