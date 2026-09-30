package A704.DODREAM.bookmark.service;

import A704.DODREAM.authorization.AuthorizationPolicy;
import A704.DODREAM.bookmark.dto.*;
import A704.DODREAM.bookmark.entity.Bookmark;
import A704.DODREAM.bookmark.repository.BookmarkRepository;
import A704.DODREAM.material.service.MaterialShareService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class BookmarkService {
    private final AuthorizationPolicy policy;
    private final BookmarkRepository bookmarks;
    private final MaterialShareService content;

    @Transactional
    public BookmarkResponse toggleBookmark(Long userId, BookmarkRequest request) {
        var material = policy.studentMaterial(userId, request.getMaterialId());
        var user = policy.actor(userId);
        var existing = bookmarks.findByUserAndMaterialAndTitleId(user, material, request.getTitleId());
        if (existing.isPresent()) {
            bookmarks.delete(existing.get());
            return BookmarkResponse.builder().bookmarkId(existing.get().getId()).isBookmarked(false).build();
        }
        var node = node(userId, material.getId(), request.getTitleId());
        var saved = bookmarks.save(Bookmark.builder().user(user).material(material).titleId(request.getTitleId())
            .title(title(node)).contents(text(node)).build());
        return BookmarkResponse.builder().bookmarkId(saved.getId()).isBookmarked(true).build();
    }
    @Transactional(readOnly = true)
    public List<BookmarkDetailResponse> getBookmarks(Long userId) {
        policy.student(userId);
        List<BookmarkDetailResponse> result = new ArrayList<>();
        for (var bookmark : bookmarks.findByUserOrderByCreatedAtDesc(policy.actor(userId))) {
            if (!policy.studentCanRead(userId, bookmark.getMaterial())) continue;
            // Do not reuse historical cached strings: old bookmarks may contain teacher answers.
            var node = find(content.getSharedMaterialJson(userId, bookmark.getMaterial().getId()).get("chapters"), bookmark.getTitleId());
            if (node == null) continue;
            result.add(new BookmarkDetailResponse(bookmark.getId(), bookmark.getMaterial().getId(),
                bookmark.getMaterial().getTitle(), bookmark.getTitleId(), title(node), text(node), bookmark.getCreatedAt()));
        }
        return result;
    }
    @Transactional(readOnly = true)
    public MaterialBookmarksResponse getMaterialBookmarks(Long userId, Long materialId) {
        var material = policy.studentMaterial(userId, materialId);
        return new MaterialBookmarksResponse(materialId, bookmarks.findByUserAndMaterial(policy.actor(userId), material)
            .stream().map(Bookmark::getTitleId).collect(Collectors.toSet()));
    }
    private Map<?, ?> node(Long userId, Long materialId, String id) {
        Map<?, ?> result = find(content.getSharedMaterialJson(userId, materialId).get("chapters"), id);
        if (result == null) throw AuthorizationPolicy.hidden();
        return result;
    }
    private Map<?, ?> find(Object value, String id) {
        if (id == null) throw AuthorizationPolicy.invalid();
        if (value instanceof Map<?, ?> map) {
            if (id.equals(String.valueOf(map.get("id")))) return map;
            for (Object child : map.values()) { Map<?, ?> found = find(child, id); if (found != null) return found; }
        } else if (value instanceof List<?> list) {
            for (Object child : list) { Map<?, ?> found = find(child, id); if (found != null) return found; }
        }
        return null;
    }
    private String title(Map<?, ?> node) {
        for (String key : List.of("title", "c_title", "s_title", "ss_title")) {
            if (node.get(key) instanceof String value) return value;
        }
        return "";
    }
    private String text(Object value) {
        if (value instanceof Map<?, ?> map) {
            List<String> parts = new ArrayList<>();
            for (var entry : map.entrySet()) {
                Object child = entry.getValue();
                if (List.of("content", "text", "question").contains(entry.getKey()) && child instanceof String string) parts.add(string);
                else if (child instanceof List || child instanceof Map) parts.add(text(child));
            }
            return String.join("\n", parts);
        }
        if (value instanceof List<?> list) return list.stream().map(this::text).collect(Collectors.joining("\n"));
        return "";
    }
}
