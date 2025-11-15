package A704.DODREAM.bookmark.controller;

import A704.DODREAM.auth.dto.request.UserPrincipal;
import A704.DODREAM.bookmark.dto.BookmarkDetailResponse;
import A704.DODREAM.bookmark.dto.BookmarkRequest;
import A704.DODREAM.bookmark.dto.BookmarkResponse;
import A704.DODREAM.bookmark.service.BookmarkService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Tag(name = "Bookmark API")
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/bookmarks")
public class BookmarkController {

    private final BookmarkService bookmarkService;

    @Operation(summary = "북마크 등록/삭제", description = "기존에 등록된 북마크인지 확인하고 등록되어 있지 않으면 등록하고, 등록되어있으면 삭제합니다.")
    @PostMapping("/toggle")
    public ResponseEntity<BookmarkResponse> toggleBookmark(
            @AuthenticationPrincipal UserPrincipal userPrincipal,
            @RequestBody BookmarkRequest request
    )
    {
        BookmarkResponse response = bookmarkService.toggleBookmark(userPrincipal.userId(), request);
        return ResponseEntity.ok(response);
    }

    @Operation(summary = "북마크 목록 조회", description = "북마크 목록을 내용과 함께 조회합니다.")
    @GetMapping
    public ResponseEntity<List<BookmarkDetailResponse>> getBookmarks(
            @AuthenticationPrincipal UserPrincipal userPrincipal
    ) {
        List<BookmarkDetailResponse> bookmarks = bookmarkService.getBookmarks(userPrincipal.userId());
        return ResponseEntity.ok(bookmarks);
    }


}
