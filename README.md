# 네이버 블로그 링크 모음

https://imwooha.github.io

[zerisun88 네이버 블로그](https://m.blog.naver.com/zerisun88)의 전체 글 링크를 모아 둔 페이지예요. 구글봇이 이 페이지의 링크를 따라 블로그 글을 찾아가게 하는 용도예요.

- `naver_blog_sitemap.py`: 네이버 블로그와 구글 블로그(zerisun.blogspot.com) 글 목록을 가져와 `index.html`, `sitemap.xml`, `robots.txt`를 만들어요.
- `update.bat`: 위 스크립트를 실행하고, 바뀐 게 있으면 커밋해서 올려요. Windows 작업 스케줄러의 `NaverBlogLinkHub` 작업이 매일 오전 9시에 실행해요. 기록은 `logs/update.log`에 남아요.

`sitemap.xml`에는 이 사이트 주소만 들어가요. 사이트맵에는 다른 도메인 주소를 넣을 수 없어서, 네이버 글은 `index.html` 안의 링크로 연결해요.
