package zzm.config;

import cn.hutool.json.JSONUtil;
import org.springframework.http.*;
import org.springframework.http.converter.AbstractGenericHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import java.io.IOException;
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.util.List;

@Configuration
public class JsonConfig implements WebMvcConfigurer {
    private static final cn.hutool.json.JSONConfig format = cn.hutool.json.JSONConfig.create()
        .setIgnoreNullValue(false).setDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

    @Override
    public void extendMessageConverters(List<HttpMessageConverter<?>> converters) {
        converters.add(0, new HutoolConverter());
    }

    private static class HutoolConverter extends AbstractGenericHttpMessageConverter<Object> {
        HutoolConverter() { super(MediaType.APPLICATION_JSON); }
        @Override protected boolean supports(Class<?> clazz) {
            return clazz != String.class && clazz != byte[].class && !Resource.class.isAssignableFrom(clazz);
        }
        @Override public Object read(Type type, Class<?> context, HttpInputMessage input) throws IOException {
            return JSONUtil.toBean(new String(input.getBody().readAllBytes(), StandardCharsets.UTF_8), type, false);
        }
        @Override protected Object readInternal(Class<?> clazz, HttpInputMessage input) throws IOException {
            return read(clazz, null, input);
        }
        @Override protected void writeInternal(Object value, Type type, HttpOutputMessage output) throws IOException {
            output.getBody().write(JSONUtil.toJsonStr(value, format).getBytes(StandardCharsets.UTF_8));
        }
    }
}
