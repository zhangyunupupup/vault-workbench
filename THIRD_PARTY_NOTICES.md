# 第三方资源

## Three.js 与 OrbitControls

- 版本：r160（0.160.0），本地原始模块中的REVISION为160。
- 来源：https://github.com/mrdoob/three.js/tree/r160
- 许可：MIT，全文随项目保存在 `web/assets/vendor/THREE-LICENSE.txt`。
- 供桌面与随手搭三维画布使用，不请求CDN。

## Windows便携版Python

- 版本：CPython 3.14.10，Windows x64官方嵌入式发行包。
- 来源：https://www.python.org/downloads/release/python-31410/
- 原始ZIP：https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip
- 原始ZIP SHA-256：`90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159`
- 原始许可和包含的第三方声明保存在发行包 `python/LICENSE.txt`。构建保留原分发文件，只将 `python314._pth` 调整为标准库、运行环境目录和工作台父目录；不启用site，不带pip。
- 依据：https://docs.python.org/3.14/using/windows.html#the-embeddable-package

## 图片与色板

桌面型号图片的官方来源及用途见 `docs/official-image-sources.md`，色板来源见 `web/assets/palette.json`。随手搭只使用程序绘制的简化外形和色值，不分发USSA STL、PDF或官方模型图片。模型库及官方PDF由用户自行准备。
