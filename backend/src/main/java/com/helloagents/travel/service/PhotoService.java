package com.helloagents.travel.service;

import com.helloagents.travel.client.UnsplashClient;
import com.helloagents.travel.dto.PhotoDataDto;
import org.springframework.stereotype.Service;

/**
 * 景点图片：两步降级检索。
 *
 * <p>顺序与旧实现一致：先 {@code "{name} China landmark"}（提高命中中国地标的概率），
 * 无结果再退化为 {@code "{name}"}。两步都失败就返回 {@code photo_url=null}，
 * 由前端渲染渐变占位图。
 */
@Service
public class PhotoService {

    private final UnsplashClient unsplashClient;

    public PhotoService(UnsplashClient unsplashClient) {
        this.unsplashClient = unsplashClient;
    }

    public PhotoDataDto photo(String name) {
        String photoUrl = unsplashClient.firstPhotoUrl(name + " China landmark");
        if (photoUrl == null) {
            photoUrl = unsplashClient.firstPhotoUrl(name);
        }
        return new PhotoDataDto(name, photoUrl);
    }
}
