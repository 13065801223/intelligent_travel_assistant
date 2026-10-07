package com.helloagents.travel.web;

import com.helloagents.travel.dto.PhotoDataDto;
import com.helloagents.travel.dto.PhotoResponseDto;
import com.helloagents.travel.service.PhotoService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 图片接口：{@code GET /api/poi/photo?name=<景点名>}。
 *
 * <p>前端用裸 {@code fetch()} 调用（Result.vue:435），并且只在 {@code success && photo_url} 时使用结果。
 * 因此本接口<b>永远返回 HTTP 200</b>：查不到就给 {@code photo_url=null}，
 * 让前端安静地退化成占位图，而不是在结果页弹一堆错误。
 */
@RestController
@RequestMapping("/api/poi")
public class PoiController {

    private final PhotoService photoService;

    public PoiController(PhotoService photoService) {
        this.photoService = photoService;
    }

    @GetMapping("/photo")
    public PhotoResponseDto photo(@RequestParam("name") String name) {
        PhotoDataDto data = photoService.photo(name);
        return new PhotoResponseDto(true, "获取图片成功", data);
    }
}
